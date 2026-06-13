from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import replace
from pathlib import Path

from app.material_catalog import MaterialRecord, sha256_file, write_catalog


TITLES = (
    "蛋白聚醣的作用", "開場動畫", "企業願景與永續責任", "全方位行動力簡報封面",
    "高峰藥品的使命與獎項", "取之於社會用之於社會", "公益活動與社會責任",
    "員工旅遊與團隊文化", "複方療法的專家", "產品線總覽", "如何選擇適合的產品",
    "潤送止痛、修護軟骨、潤滑關節", "退化性關節炎分級與建議", "美白抗皺、消除疲痛、增強肌耐力",
    "全素可食、關節照護、脫手自如", "愛屋及烏、照顧寵物家人",
    "預防感冒、調節過敏、增強免疫力", "使用經驗分享", "鎮定安神、幫助入睡、深度熟睡",
    "疫情期間焦慮失眠風險", "疫情焦慮失眠與緊張", "櫻桃汁與褪黑激素",
    "櫻桃汁改善睡眠品質", "Sleep HA 全方位改善睡眠品質", "Sleep HA 診所體驗分享",
    "Sleep HA 使用經驗分享", "鎮定安神、幫助入睡、深度熟睡", "提升睪固酮與男性健康",
    "健福診所改善案例", "GOODHA Post Market Study", "新冠肺炎與傳染病風險",
    "消除疲勞、肝炎輔助治療、逆轉肝硬化", "臨床案例：自抗原腎癌",
    "臨床案例：GOT/GPT下降", "冬蟲夏草原料比較", "補充維生素B的好處",
    "降尿酸、減少痛風發作、保護腎臟", "實際改善案例", "如何選擇適合的產品",
    "退化性關節炎整合照護", "口服玻尿酸的專家", "什麼是玻尿酸",
    "玻尿酸驚人之處與保水能力", "玻尿酸是老化的指標", "玻尿酸體內與自然界分布",
    "關節炎流行病學", "骨關節炎盛行率", "關節滑液", "退化性關節炎與軟骨分解",
    "退化性關節炎發炎機轉", "退化性關節炎與軟骨細胞", "金屬蛋白酶形成機轉",
    "軟骨退化訊號路徑", "玻尿酸抑制發炎的研究", "A+HA 產品定位",
    "玻尿酸分子與保水量", "玻尿酸是老化指標", "口服玻尿酸吸收實驗：美國",
    "口服玻尿酸吸收實驗：日本", "口服玻尿酸吸收實驗：中國", "口服玻尿酸吸收機制",
    "口服玻尿酸如何吸收及合成", "口服玻尿酸臨床實證統合分析",
    "口服玻尿酸臨床實證研究", "硫酸化葡萄糖胺吸收率限制",
    "玻尿酸合成酵素", "葡萄糖胺促進玻尿酸原料", "年輕女性玻尿酸合成情況",
    "中老年女性玻尿酸合成情況", "中老年婦女使用口服小分子玻尿酸",
    "A+HA 小分子液體口服玻尿酸", "膝關節男女老化差異", "關節炎男女老化差異",
    "Epidemiology of osteoarthritis", "關節軟骨結構", "關節軟骨之膠原結構",
    "蛋白聚醣是關節重要物質", "蛋白聚醣的作用", "目前玻尿酸治療上的障礙",
    "口服玻尿酸的安全選擇", "如何選擇適合的產品", "Q10HA 產品與行動力",
    "女性族群最關心的三大議題", "Q10HA 小分子液體口服玻尿酸",
    "退化性關節炎源自肌力減少", "Coenzyme Q10 的功能", "補充Q10提升肌耐力",
    "Q10改善疲勞與腰痠肩痛案例", "A+HA與Q10HA關節問題整合",
    "A+HA與Q10HA行動力整合", "Q10增加行動力臨床使用案例", "如何選擇適合的產品",
    "YESHA 素的玻尿酸新品", "YESHA 包裝與外觀", "YESHA 產品衛教摺頁",
    "YESHA 與Q10HA研究素材", "愛老婆的知名藝人也知道肌肉對骨關節的重要",
    "轉場動畫", "iMuso 肌不可失產品封面", "肌少症在台灣",
    "肌少症在台灣的影響", "台灣肌少症機率與盛行率", "肌少症篩檢流程",
    "歐盟肌少症SARC-F問卷", "2019亞洲肌少症共識", "老年的隱性殺手肌少症",
    "肌少症發生的主要原因", "肌少症發生原因與路徑", "老年合併糖尿病與肌少症風險",
    "肌肉量隨年齡衰退", "肌少症症狀", "肌少症與退化性關節炎息息相關",
    "肌肉不夠力關節磨損更嚴重", "適度運動預防膝關節炎發生",
    "退化性關節炎源自肌力減少", "肌肉量決定活多久", "肌肉力量減弱增加關節負擔",
    "增強肌耐力減少關節疾病發生", "搶救退化性關節炎先強化肌肉",
    "搶救退化性關節炎強化肌肉", "肌少症發生的主要原因",
    "老年合併糖尿病與肌少症風險", "吃蛋白質就能長肌肉嗎",
    "如何預防或改善肌少症", "肌肉增強的關鍵營養素", "醫療級配方改善肌少症",
    "胺基酸的重要性與來源", "胺基酸與運動的重要性", "肌肉生長關鍵因子白胺酸與精胺酸",
    "攝取量足才能達到Leucine Trigger", "白胺酸在食物中的含量",
    "白胺酸增加肌力恢復行動力", "白胺酸有效改善肌少症",
    "肌肉生長關鍵因子白胺酸與精胺酸", "IGF-1參與肌肉與骨骼生長",
    "如何增加IGF-1分泌", "Arginine能增加IGF-1", "Arginine搭配重量訓練與IGF-1",
    "乳清蛋白合成肌肉的原料", "老人要比一般人攝取更多蛋白質",
    "乳清蛋白富含白胺酸", "乳清蛋白加運動增加肌肉纖維合成效率",
    "黃金比例高劑量白胺酸與乳清蛋白", "蛋白質一日攝取量",
    "何謂BCAA", "BCAA在人體的角色", "Benefits of BCAAs", "常見的BCAA功效",
    "肌肉生長四大關鍵", "iMuso胺基酸醫療級配方", "蛋白質該如何攝取",
    "台灣常見的三餐", "三餐平均攝取蛋白質增加效果最佳",
    "茹素者的蛋白質攝取量不足", "運動後補充需立即補充蛋白質",
    "茹素者的蛋白質攝取量不足", "用法用量", "使用者體驗分享",
    "iMuso增加肌肉量提升免疫力", "iMuso適用族群",
    "iMuso一手四足效果說明", "iMuso與A+HA、Q10HA搭配方法",
    "三折頁正面", "三折頁背面", "Thank you for your attention",
    "診所肌少症相關產品：固力健", "診所肌少症相關產品：肌力加",
    "診所肌少症相關產品：胺舒寧", "好市多蛋白質補充品", "常見產品比較",
    "產品文件掃描", "蛋白質與胺基酸", "蛋白質的生物功能", "蛋白質代謝路徑",
    "蛋白質一日攝取量", "胺基酸藥品與腎臟照護", "Q&A",
    "肌少症篩檢流程", "歐盟肌少症SARC-F問卷", "2019亞洲肌少症共識",
    "SPPB簡短身體功能量表", "平衡測驗", "走路速度", "坐站測驗",
    "下肢肌肉功能評估", "iMuso一手四足效果說明", "IGF-1增加癌症風險",
    "乳糖不耐症", "mTOR", "肌肉生長四大關鍵",
    "增強肌肉能提升免疫力嗎", "肌肉活化與免疫細胞", "糖尿病患更應補充蛋白質",
    "白胺酸不影響體內葡萄糖生作用", "影片素材",
)

BLANK_OR_TEMPLATE = {2, 12, 14, 15, 16, 17, 19, 27, 28, 32, 37, 46, 55, 90, 98, 195}
CASE_OR_PRIVATE = {18, 25, 26, 29, 33, 34, 38, 88, 91, 158, 171}
COMPETITOR = {9, 10, 11, 35, 36, 39, 166, 167, 168, 169, 170}
STRONG_CLAIM = {
    20, 21, 22, 23, 24, 31, 54, 63, 64, 72, 73, 83, 84, 85, 87, 97,
    109, 133, 187, 191, 192, 193, 194,
}
DENSE_RESEARCH = set(range(42, 81)) | set(range(100, 159)) | set(range(172, 195))
SENDABLE = {
    3, 4, 5, 6, 7, 8, 40, 41, 45, 47, 48, 56, 71, 75, 77, 79, 80,
    82, 93, 94, 99, 103, 105, 106, 110, 111, 112, 113, 115, 116, 117,
    118, 119, 120, 123, 124, 127, 128, 131, 139, 140, 144, 149, 150,
    152, 153, 154, 155, 156, 157, 159, 160, 161, 162, 163, 164, 165,
    172, 173, 174, 175, 177, 178, 179, 180, 181, 182, 183, 184, 185,
    186, 189, 190,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the external LINE material catalog.")
    parser.add_argument("--root", required=True, help="Directory containing 投影片1.JPG ... 投影片195.JPG.")
    parser.add_argument("--output", default="data/line_material_catalog.json")
    args = parser.parse_args(argv)

    root = Path(args.root)
    if not root.exists():
        raise FileNotFoundError(f"Material directory not found: {root}")
    if len(TITLES) != 195:
        raise RuntimeError(f"Expected 195 material titles, got {len(TITLES)}.")

    records = []
    hashes: dict[str, list[int]] = defaultdict(list)
    for slide in range(1, 196):
        path = root / f"投影片{slide}.JPG"
        if not path.exists():
            raise FileNotFoundError(f"Missing source slide: {path}")
        digest = sha256_file(path)
        hashes[digest].append(slide)
        records.append(_record(slide, digest))

    canonical_by_slide = {}
    for slides in hashes.values():
        canonical = slides[0]
        for slide in slides[1:]:
            canonical_by_slide[slide] = f"MAT-ACT-{canonical:03d}"
    records = [
        replace(record, duplicate_of=canonical_by_slide.get(index, ""))
        for index, record in enumerate(records, start=1)
    ]
    output = write_catalog(args.output, records)
    print(f"catalog={output}")
    print(f"records={len(records)}")
    return 0


def _record(slide: int, digest: str) -> MaterialRecord:
    title = TITLES[slide - 1]
    product, topic, audience = _classify(slide, title)
    sendability = "sendable" if slide in SENDABLE else "internal_only"
    review_status = "pending_review"
    risk = "medium"
    flags = ["human_review_required"]
    comment = "可作為拜訪後的輔助素材，送出前需確認對象與文案。"

    if slide in BLANK_OR_TEMPLATE:
        sendability = "blocked"
        review_status = "blocked"
        risk = "high"
        flags.append("blank_or_template")
        comment = "空白、轉場或未完成版面，不得直接對外發送。"
    elif slide in CASE_OR_PRIVATE:
        sendability = "blocked"
        review_status = "blocked"
        risk = "high"
        flags.append("patient_privacy_risk")
        comment = "含個案、表單或可識別內容，只能內部查閱。"
    elif slide in COMPETITOR:
        sendability = "internal_only"
        risk = "high"
        flags.append("competitor_comparison_risk")
        comment = "含競品或產品比較，需法規與主管審核後才能使用。"
    elif slide in STRONG_CLAIM:
        sendability = "internal_only"
        risk = "high"
        flags.append("medical_overclaim_risk")
        comment = "含強療效、疾病或風險敘述，只供內部訓練與人工改寫。"
    elif slide in DENSE_RESEARCH:
        sendability = "internal_only" if slide not in SENDABLE else "sendable"
        risk = "medium"
        flags.append("dense_clinical_reference")
        comment = "研究或臨床資訊密度高，應搭配簡短說明並由人員確認。"
    else:
        risk = "low" if slide in SENDABLE else "medium"

    caption = _caption(product, topic, audience, sendability)
    campaigns = ("行動力",)
    triggers = ("continue_topic", "activity_followup", "usage_reminder")
    return MaterialRecord(
        material_id=f"MAT-ACT-{slide:03d}",
        filename=f"投影片{slide}.JPG",
        sha256=digest,
        duplicate_of="",
        product=product,
        topic=topic,
        audience=audience,
        visual_summary=f"簡報頁面「{title}」，主題為{topic}。",
        internal_comment=comment,
        customer_caption=caption,
        risk_level=risk,
        safety_flags=tuple(flags),
        sendability=sendability,
        review_status=review_status,
        test_result="not_tested",
        campaigns=campaigns,
        trigger_types=triggers,
    )


def _classify(slide: int, title: str) -> tuple[str, str, str]:
    if slide <= 11:
        return "品牌/全產品", title, "醫療專業人員與合作夥伴"
    if slide <= 39:
        if "Sleep" in title or "睡眠" in title or "失眠" in title or "褪黑" in title:
            return "SleepHA", title, "睡眠照護相關客戶"
        if "GOOD" in title.upper() or "感冒" in title or "過敏" in title:
            return "GOODHA/TOPHA", title, "家醫科、耳鼻喉科與藥局"
        return "全產品", title, "醫療專業人員"
    if slide <= 92:
        return "A+HA/Q10HA", title, "骨科、復健科、家醫科與藥局"
    if slide <= 98:
        return "YESHA", title, "全素需求與關節照護客戶"
    return "iMuso", title, "高齡、肌少症、復健與營養照護客戶"


def _caption(product: str, topic: str, audience: str, sendability: str) -> str:
    if sendability == "blocked":
        return "此素材僅供內部辨識，請勿直接傳送。"
    return (
        f"您好，這張資料整理的是「{topic}」的重點，"
        f"可作為{audience}的簡短參考。若您有需要，我再把 {product} "
        "相關內容整理成更精簡的版本。"
    )


if __name__ == "__main__":
    raise SystemExit(main())
