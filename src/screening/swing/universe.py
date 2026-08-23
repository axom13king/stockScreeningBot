"""スイングスクリーニングの母集団(TOPIX500相当)を構築する。

J-Quants /equities/master のScaleCat(規模区分)で絞り込む。
価格データではない「マスタ」情報のため、無料プランの3ヶ月遅延制限の対象外。
"""

from src.data.jquants import JQuantsClient


def build_universe(cfg: dict) -> list[dict]:
    client = JQuantsClient()
    master = client.get_listed_info()
    scale_categories = set(cfg["universe"]["scale_categories"])

    universe = []
    for row in master:
        if row.get("ScaleCat") not in scale_categories:
            continue
        code = row.get("Code", "")
        code4 = code[:4]  # v2の5桁コード(末尾は株式種別)を4桁の通常コードに正規化
        universe.append(
            {
                "code": code4,
                "name": row.get("CoName"),
                "sector_code": row.get("S33"),
                "sector_name": row.get("S33Nm"),
            }
        )
    return universe
