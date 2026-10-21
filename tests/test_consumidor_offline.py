"""Download do Consumidor.gov.br sem rede real: offline com bronze, sem bronze, .part, retomada, republicação e 416.

Uso: python -I tests/test_consumidor_offline.py   (urlopen é trocado por um falso; nenhum acesso à rede)
"""
import sys
import tempfile
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))  # -I tira o diretório do script do sys.path
import ingest_consumidor as ic  # noqa: E402

DADOS = bytes(range(256)) * 12  # 3.072 bytes
chamadas = []


class Resp:
    def __init__(self, corpo, status=200, cair_em=None):
        self.corpo, self.status, self.cair_em, self.pos = corpo, status, cair_em, 0
        self.headers = {"Content-Length": str(len(DADOS))}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, n):
        if self.cair_em is not None and self.pos >= self.cair_em:
            raise ConnectionResetError("caiu")
        fim = len(self.corpo) if self.cair_em is None else min(len(self.corpo), self.cair_em)
        bloco = self.corpo[self.pos:min(self.pos + 1000, fim)]
        self.pos += len(bloco)
        return bloco


def servidor(cair_primeiro=False, recusar_range=0):
    estado = {"get": 0, "416": recusar_range}

    def urlopen(req, timeout=None):
        chamadas.append((req.get_method(), req.full_url, req.get_header("Range")))
        if req.get_method() == "HEAD":
            return Resp(b"")
        rng = req.get_header("Range")
        if rng and estado["416"]:
            estado["416"] -= 1
            raise urllib.error.HTTPError(req.full_url, 416, "Range Not Satisfiable", {}, None)
        estado["get"] += 1
        if rng:
            return Resp(DADOS[int(rng[6:-1]):], status=206)
        return Resp(DADOS, cair_em=1000 if cair_primeiro and estado["get"] == 1 else None)
    return urlopen


def sem_rede(req, timeout=None):
    chamadas.append((req.get_method(), req.full_url, None))
    raise urllib.error.URLError("rede bloqueada no teste")


# 1. Bronze real presente e sem rede: 2024 e 2025 não tocam a rede; 2026 (ausente) avisa e segue.
ic.urllib.request.urlopen = sem_rede
reais = sorted(ic.BRONZE.glob("dadosconsumidor*.csv"))
assert reais, "rode antes pipelines/ingest_consumidor.py (precisa do bronze local)"
ic.baixar()
assert all("2026" in url for _, url, _ in chamadas), chamadas

with tempfile.TemporaryDirectory() as tmp:
    ic.BRONZE, ic.ANOS = Path(tmp), [2024]
    alvo, part = Path(tmp) / "dadosconsumidor2024.csv", Path(tmp) / "dadosconsumidor2024.csv.part"

    # 2. Sem rede e sem bronze: erro claro.
    try:
        ic.baixar()
        raise AssertionError("devia falhar sem rede e sem bronze")
    except SystemExit as e:
        assert "sem bronze" in str(e)

    # 3. Conexão cai no meio: fica no .part, retoma com Range e só então renomeia.
    ic.urllib.request.urlopen = servidor(cair_primeiro=True)
    chamadas.clear()
    ic.baixar()
    assert alvo.read_bytes() == DADOS and not part.exists()
    assert ("GET", ic.URL.format(y=2024), "bytes=1000-") in chamadas, chamadas

    # 4. Com o final presente e sem --force: nenhuma chamada.
    chamadas.clear()
    ic.baixar()
    assert chamadas == []

    # 5. Republicação (tamanho remoto diferente) com --force: baixa do zero, nunca anexa ao antigo.
    alvo.write_bytes(b"versao antiga")
    ic.urllib.request.urlopen = servidor()
    ic.baixar(force=True)
    assert alvo.read_bytes() == DADOS

    # 6. .part órfão que o servidor recusa (416): apaga e recomeça uma vez.
    alvo.unlink()
    part.write_bytes(b"lixo de outra versao")
    ic.urllib.request.urlopen = servidor(recusar_range=1)
    ic.baixar()
    assert alvo.read_bytes() == DADOS and not part.exists()

    # 7. 416 de novo depois de recomeçar: erro sugerindo --force.
    alvo.unlink()
    part.write_bytes(b"lixo")
    ic.urllib.request.urlopen = servidor(cair_primeiro=True, recusar_range=2)
    try:
        ic.baixar()
        raise AssertionError("devia falhar no segundo 416")
    except SystemExit as e:
        assert "--force" in str(e)

print("consumidor offline ok")
