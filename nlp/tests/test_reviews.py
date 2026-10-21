"""Teste do leitor de export e do classificador com fixtures FICTÍCIOS. Uso: python -I nlp/tests/test_reviews.py"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "pipelines"), str(ROOT / "nlp")]  # -I tira o diretório do script do sys.path
from build_gold import checar_contrato  # noqa: E402
from ingest_reviews_export import anonimizar, ingerir  # noqa: E402
from reviews_sentiment import gold, sentimento, temas  # noqa: E402

AQUI = Path(__file__).parent

with tempfile.TemporaryDirectory() as tmp:
    play16 = Path(tmp) / "reviews_exemplo_202601.csv"  # o export real do Play vem em UTF-16
    play16.write_text((AQUI / "fixture_play.csv").read_text(encoding="utf-8"), encoding="utf-16")
    df = ingerir([play16, AQUI / "fixture_appstore.json"], saida=Path(tmp) / "silver.parquet")
    assert len(df) == 20 and set(df.fonte) == {"google_play", "app_store"}, df.fonte.value_counts()
    erros = checar_contrato(ROOT / "contracts" / "export_reviews.yaml", parquet=Path(tmp) / "silver.parquet")
    assert not erros, erros
    todo = " ".join(df.texto)
    for vazou in ["fulano.teste@exemplo.com", "123.456.789-09", "98765-4321", "Maria", "XK7Q2P", "apelido", "Pedro"]:
        assert vazou not in todo, vazou
    assert "[email]" in todo and "[cpf]" in todo and "[telefone]" in todo and "[nome]" in todo
    assert "[localizador]" in todo
    g = gold(df, saida=Path(tmp) / "gold.parquet")
    erros = checar_contrato(ROOT / "contracts" / "export_review_themes.yaml", parquet=Path(tmp) / "gold.parquet")
    assert not erros, erros
    assert g.reviews.sum() > len(df)  # multirrótulo: algum review conta em 2+ temas

assert temas("O voo atrasou e a mala sumiu") == ["atraso/cancelamento", "bagagem"]
assert temas("Pedi reembolso pelo app") == ["reembolso", "canais de venda/app"]
assert temas("Voo pontual, tripulação gentil") == ["outro"]  # "pontual" não é pontos/resgate
assert temas("Juntei 10 mil pontos") == ["pontos/resgate"]
assert temas("Viagem tranquila") == ["outro"]
assert temas("Resgatei pontos") == ["pontos/resgate"]
assert temas("Muito caro") == ["preco"]
assert temas("Atendimento demorou") == ["atendimento"]
assert sentimento(1, "voo atrasou") == "negativo"
assert sentimento(5, "Gostei") == "positivo"
assert sentimento(3, "Não funciona direito") == "negativo"  # negação inverte "funciona"
assert sentimento(3, "Bom, mas o preço subiu") == "positivo"
assert sentimento(5, "Péssimo, horrível, voo cancelado") == "negativo"  # nota alta, texto de reclamação
assert sentimento(2, "Ótimo, excelente, recomendo") == "neutro"
assert anonimizar("meu nome é João Silva") == "meu nome é [nome]"
assert anonimizar("Atendente muito educada") == "Atendente muito educada"  # minúscula após gatilho não é nome
print("reviews ok")
