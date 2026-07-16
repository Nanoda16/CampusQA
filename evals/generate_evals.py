"""
Generate 50 evaluation test cases for the campus QA RAG system.

Groups:
  - 30 single-turn knowledge questions (answerable from knowledge_docs/)
  - 10 multi-turn conversation questions (2-3 exchanges + final query)
  - 10 out-of-domain (OOD) questions (knowledge base cannot answer)
"""
from __future__ import annotations

import json

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def make_single(
    id: str,
    question: str,
    gold_title_contains: str,
    expected_terms: list[str],
) -> dict:
    return {
        "id": id,
        "group": "single_turn",
        "question": question,
        "answerable": True,
        "gold_title_contains": gold_title_contains,
        "expected_terms": expected_terms,
    }


def make_multi(
    id: str,
    history: list[dict],
    question: str,
    gold_title_contains: str,
    expected_terms: list[str],
) -> dict:
    return {
        "id": id,
        "group": "multi_turn",
        "history": history,
        "question": question,
        "answerable": True,
        "gold_title_contains": gold_title_contains,
        "expected_terms": expected_terms,
    }


def make_ood(id: str, question: str) -> dict:
    return {
        "id": id,
        "group": "ood",
        "question": question,
        "answerable": False,
        "gold_title_contains": "",
        "expected_terms": [],
    }


# ===========================================================================
# 30 SINGLE-TURN questions — each traceable to real knowledge_docs content
# ===========================================================================

single_turn: list[dict] = [
    # ----- University info / culture -----
    make_single(
        "q001",
        "河海大学的校训是什么？",
        "校园文化",
        ["艰苦朴素", "实事求是", "严格要求", "勇于探索"],
    ),
    make_single(
        "q002",
        "河海大学校训中「艰苦朴素」的含义是什么？",
        "校园文化",
        ["艰苦朴素", "生活准则"],
    ),
    make_single(
        "q003",
        "河海大学校歌的名称是什么？",
        "校园文化",
        ["大哉河海奔前程"],
    ),
    make_single(
        "q004",
        "河海大学校徽是什么形状的？",
        "校园文化",
        ["梅花形"],
    ),
    make_single(
        "q005",
        "河海大学校徽中的蓝色系叫什么名字？",
        "校园文化",
        ["河海蓝"],
    ),
    # ----- History / overview (third_party/河海大学.md = Wikipedia) -----
    make_single(
        "q006",
        "河海大学是哪一年创办的？",
        "河海大学",
        ["1915"],
    ),
    make_single(
        "q007",
        "河海大学的创办人是谁？",
        "河海大学",
        ["张謇"],
    ),
    make_single(
        "q008",
        "河海大学的前身是什么？",
        "河海大学",
        ["河海工程专门学校"],
    ),
    make_single(
        "q009",
        "河海大学现任校长是谁？",
        "河海大学",
        ["郑金海"],
    ),
    make_single(
        "q010",
        "河海大学现任党委书记是谁？",
        "河海大学",
        ["杨桂山"],
    ),
    make_single(
        "q011",
        "河海大学的校庆日是哪一天？",
        "河海大学",
        ["10月27日"],
    ),
    make_single(
        "q012",
        "河海大学有几个校区？分别在哪些城市？",
        "校园文化",
        ["南京", "常州"],
    ),
    # ----- Campus addresses -----
    make_single(
        "q013",
        "河海大学西康路校区的地址是什么？",
        "校园文化",
        ["西康路1号"],
    ),
    make_single(
        "q014",
        "河海大学常州校区的地址是什么？",
        "校园文化",
        ["金坛区", "河海大道1915号"],
    ),
    # ----- News: 新疆研究院 -----
    make_single(
        "q015",
        "河海大学新疆研究院是哪一年揭牌成立的？",
        "河海大学新疆研究院揭牌成立",
        ["2026"],
    ),
    make_single(
        "q016",
        "河海大学新疆研究院依托哪些优势学科？",
        "河海大学新疆研究院揭牌成立",
        ["水利工程", "环境科学与工程", "农业工程"],
    ),
    # ----- News: 国家科技奖 -----
    make_single(
        "q017",
        "2025年度国家科学技术奖河海大学共有几项成果获奖？",
        "4项成果荣获国家科学技术奖",
        ["4项", "国家科技进步奖"],
    ),
    make_single(
        "q018",
        "董增川教授团队牵头的获奖项目名称是什么？",
        "4项成果荣获国家科学技术奖",
        ["河流功能完整性重构"],
    ),
    # ----- News: 储能新专业 -----
    make_single(
        "q019",
        "河海大学获批了什么本科新专业？",
        "河海大学获批储能科学与工程本科新专业",
        ["储能科学与工程"],
    ),
    make_single(
        "q020",
        "储能科学与工程专业依托哪个学院？",
        "河海大学获批储能科学与工程本科新专业",
        ["新能源学院"],
    ),
    # ----- News: AI for Water -----
    make_single(
        "q021",
        "AI for Water学术联盟有多少家初始成员？",
        "AI_for_Water学术联盟成立大会",
        ["29"],
    ),
    make_single(
        "q022",
        "AI for Water学术联盟的理事长单位是哪所大学？",
        "AI_for_Water学术联盟成立大会",
        ["河海大学"],
    ),
    # ----- News: 挑战杯 -----
    make_single(
        "q023",
        "河海大学在第十五届「挑战杯」江苏省赛中获得多少个特等奖？",
        "河海大学获挑战杯江苏省特等奖4项",
        ["4项", "特等奖"],
    ),
    # ----- News: 出访挪威 -----
    make_single(
        "q024",
        "2026年4月河海大学代表团出访了哪个国家？",
        "河海大学代表团出访挪威",
        ["挪威"],
    ),
    # ----- News: 魏长赟教授获奖 -----
    make_single(
        "q025",
        "魏长赟教授获得了英国ICE学会的什么奖项？",
        "我校魏长赟教授荣获英国ICE学会年度哈尔克罗爵士奖",
        ["哈尔克罗爵士奖", "Halcrow Prize"],
    ),
    # ----- News: 张建云院士 -----
    make_single(
        "q026",
        "张建云院士荣获了第十六届什么奖项？",
        "张建云院士荣获第十六届光华工程科技奖",
        ["光华工程科技奖"],
    ),
    # ----- News: 陈永辉教授 -----
    make_single(
        "q027",
        "我校陈永辉教授在2026年荣获了什么省级荣誉称号？",
        "我校陈永辉教授荣获2026年江苏省先进工作者",
        ["江苏省先进工作者"],
    ),
    # ----- Alumni: 徐芝纶教育基金 -----
    make_single(
        "q028",
        "徐芝纶教育基金是哪一年设立的？",
        "徐芝纶教育基金",
        ["1996"],
    ),
    # ----- 常用电话 -----
    make_single(
        "q029",
        "河海大学西康路校区医疗服务电话是什么？",
        "常用电话",
        ["83787120"],
    ),
    # ----- 毕业典礼 -----
    make_single(
        "q030",
        "河海大学2026届本科生毕业典礼上郑金海校长演讲的题目是什么？",
        "河海大学举行2026届本科生毕业典礼",
        ["保持好奇心", "增强思辨力"],
    ),
]

# ===========================================================================
# 10 MULTI-TURN questions — conversational context + follow-up query
# ===========================================================================

multi_turn: list[dict] = [
    make_multi(
        "mt001",
        [
            {"role": "user", "content": "河海大学新疆研究院是什么时候成立的？"},
            {"role": "assistant", "content": "河海大学新疆研究院于2026年5月15日在乌鲁木齐揭牌成立。"},
        ],
        "这个研究院主要聚焦什么方向？",
        "河海大学新疆研究院揭牌成立",
        ["新疆", "水利", "农业"],
    ),
    make_multi(
        "mt002",
        [
            {"role": "user", "content": "河海大学在2025年国家科技奖中表现如何？"},
            {"role": "assistant", "content": "河海大学共有4项成果获得2025年度国家科学技术奖。"},
        ],
        "土木与交通学院陈永辉教授团队的获奖成果是什么？",
        "4项成果荣获国家科学技术奖",
        ["淤泥软土", "固化"],
    ),
    make_multi(
        "mt003",
        [
            {"role": "user", "content": "河海大学有几个校区？"},
            {"role": "assistant", "content": "河海大学有三个校区：西康路校区、江宁校区和常州校区。"},
            {"role": "user", "content": "常州校区的具体地址是什么？"},
            {"role": "assistant", "content": "常州校区位于江苏省常州市金坛区河海大道1915号。"},
        ],
        "江宁校区的地址是什么？",
        "校园文化",
        ["佛城西路8号", "江宁"],
    ),
    make_multi(
        "mt004",
        [
            {"role": "user", "content": "河海大学代表团2026年出访了哪里？"},
            {"role": "assistant", "content": "2026年4月河海大学代表团出访了挪威。"},
        ],
        "代表团访问了挪威哪两所大学？",
        "河海大学代表团出访挪威",
        ["奥斯陆大学", "卑尔根大学"],
    ),
    make_multi(
        "mt005",
        [
            {"role": "user", "content": "什么是AI for Water学术联盟？"},
            {"role": "assistant", "content": "AI for Water学术联盟是一个专注于人工智能与水利交叉领域的学术组织。"},
        ],
        "这个联盟有多少家初始成员？其中理事长单位是哪所大学？",
        "AI_for_Water学术联盟成立大会",
        ["29", "河海大学"],
    ),
    make_multi(
        "mt006",
        [
            {"role": "user", "content": "河海大学在第十五届挑战杯江苏省赛中成绩怎么样？"},
            {"role": "assistant", "content": "河海大学获得特等奖4项、一等奖4项。"},
        ],
        "获得特等奖的「深海哨兵」项目是哪个学院推报的？",
        "河海大学获挑战杯江苏省特等奖4项",
        ["港口海岸与近海工程学院"],
    ),
    make_multi(
        "mt007",
        [
            {"role": "user", "content": "河海大学校徽有什么特点？"},
            {"role": "assistant", "content": "河海大学校徽为梅花形图案，选取河海蓝为标准色。"},
        ],
        "校徽中间的图案是什么字体的什么字？",
        "校园文化",
        ["篆字", "河海"],
    ),
    make_multi(
        "mt008",
        [
            {"role": "user", "content": "河海大学2026年本科生毕业典礼是什么时候举行的？"},
            {"role": "assistant", "content": "2026届本科生毕业典礼于2026年6月22日举行。"},
        ],
        "毕业典礼上郑金海校长的演讲主题是什么？他提出了哪三点希望？",
        "河海大学举行2026届本科生毕业典礼",
        ["好奇心", "思辨力", "勤学"],
    ),
    make_multi(
        "mt009",
        [
            {"role": "user", "content": "河海大学有什么教育基金？"},
            {"role": "assistant", "content": "河海大学设有徐芝纶教育基金、严恺教育科技基金、钱正英教育科技基金等多个基金。"},
        ],
        "徐芝纶教育基金是哪一年设立的？",
        "徐芝纶教育基金",
        ["1996"],
    ),
    make_multi(
        "mt010",
        [
            {"role": "user", "content": "听说河海大学获批了一个新专业？"},
            {"role": "assistant", "content": "河海大学获批了储能科学与工程本科新专业。"},
            {"role": "user", "content": "这个专业属于哪个学院？"},
            {"role": "assistant", "content": "该专业依托新能源学院。"},
        ],
        "加上这个新专业，河海大学目前本科专业总数是多少？",
        "河海大学获批储能科学与工程本科新专业",
        ["73"],
    ),
]

# ===========================================================================
# 10 OOD questions — plausible student queries that the KB cannot answer
# ===========================================================================

ood: list[dict] = [
    make_ood("ood001", "河海大学今年在江苏的录取分数线是多少？"),
    make_ood("ood002", "河海大学附近有什么好吃的餐馆推荐？"),
    make_ood("ood003", "河海大学宿舍是几人间？有没有空调和独立卫生间？"),
    make_ood("ood004", "河海大学研究生学费一年多少钱？"),
    make_ood("ood005", "河海大学有哪些学生社团？怎么加入？"),
    make_ood("ood006", "河海大学毕业生的平均就业率和薪资是多少？"),
    make_ood("ood007", "河海大学有没有游泳馆？开放时间是什么时候？"),
    make_ood("ood008", "河海大学在2026年武书连大学排名中排第几？"),
    make_ood("ood009", "河海大学的奖学金具体有哪些类别？金额分别是多少？"),
    make_ood("ood010", "河海大学转专业的具体条件和流程是什么？"),
]

# ===========================================================================
# Combine & write
# ===========================================================================

all_cases = single_turn + multi_turn + ood

with open("evals/campus_qa.jsonl", "w", encoding="utf-8") as f:
    for case in all_cases:
        f.write(json.dumps(case, ensure_ascii=False) + "\n")

print(f"Total cases: {len(all_cases)}")
print(f"  Single-turn: {len(single_turn)}")
print(f"  Multi-turn:  {len(multi_turn)}")
print(f"  OOD:         {len(ood)}")

# Validate
import json as _json
data = [_json.loads(l) for l in open("evals/campus_qa.jsonl", encoding="utf-8")]
assert len(data) == 50, f"Expected 50, got {len(data)}"
groups = {}
for d in data:
    groups.setdefault(d["group"], []).append(d["id"])
for g, ids in groups.items():
    print(f"  {g}: {len(ids)} items ({ids[0]}..{ids[-1]})")
print("Validation PASSED")
