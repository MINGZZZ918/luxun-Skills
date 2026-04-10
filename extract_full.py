#!/usr/bin/env python3
"""
从《鲁迅全集》txt 抽取全部 299 篇（剔除编者前言），按集分类输出。

输出结构：
references/works/
├── INDEX.md
├── 01-nahan-panghuang/      # 呐喊·彷徨（小说）
├── 02-gushi-xinbian/        # 故事新编
├── 03-zawen/                # 杂文（横跨《坟》《热风》《华盖集》等）
├── 04-zhaohua-xishi/        # 朝花夕拾
├── 05-yecao/                # 野草
├── 06-shige/                # 新诗 + 旧体诗
├── 07-yanjiang/             # 演讲
└── 08-xuba-tongxun/         # 序跋与通讯

清洗规则同前版。
多 part 章节（如 "狂人日记(1)" "(2)"）自动合并。
"""
import re
import sys
from pathlib import Path
from collections import OrderedDict

SRC = Path("/mnt/user-data/uploads/鲁迅全集.txt")
OUT_ROOT = Path("/home/claude/luxun-skill/references/works")

# 集合划分（章号区间 → 目录名 → 显示名）
SECTIONS = [
    (2,   38,  "01-nahan-panghuang", "呐喊·彷徨"),
    (39,  48,  "02-gushi-xinbian",   "故事新编"),
    (49,  176, "03-zawen",           "杂文"),
    (177, 186, "04-zhaohua-xishi",   "朝花夕拾"),
    (187, 208, "05-yecao",           "野草"),
    (209, 237, "06-shige",           "诗歌"),
    (238, 249, "07-yanjiang",        "演讲"),
    (250, 300, "08-xuba-tongxun",    "序跋与通讯"),
]

# ============ 清洗正则（沿用并加强） ============

JUNK_LINE_PATTERNS = [
    re.compile(r"xiaoshuo", re.IGNORECASE),
    re.compile(r"小[\W_]*说[\W_]*天[\W_]*堂"),
    re.compile(r"^[wWｗＷ][\W_]*[wWｗＷ]", re.MULTILINE),
    re.compile(r"txt[\W_]*小"),
]

EDITOR_NOTE = re.compile(r"【按语】.*", re.DOTALL)

WESTERN_INLINE = re.compile(r"[a-z][a-z\s\.\-]{3,}[a-z]")
WESTERN_PAREN = re.compile(r'（[a-z][a-z\s\.\,\-]{2,}）')
WESTERN_DOUBLE_NOTE = re.compile(
    r'[a-z]{4,}[a-z]+：[^\n]*?（\d{4}[^）]*）[^\n]*?[一二三四五六七八九十百千万]?[文书诗篇集语段记]。'
)
WESTERN_DOUBLE_NOTE_SHORT = re.compile(
    r'[a-z]{4,}[a-z]+：[^\n]{0,200}?[。！？]'
)
NAME_NOTE = re.compile(r'（\d{4}[─\-—]?\d{0,4}）：[^。！？]*[。！？]')
QUOTED_NOTE = re.compile(
    r'\u201c[^\u201c\u201d]{1,40}\u201d：(?![\u201c])[^。！？\n]{0,300}[。！？]'
)
DUP_CN = re.compile(r"([\u4e00-\u9fa5]{2,5})\1")

# 历史名词注释：词后跟 "：旧时/古时/清代/明代/语见/语出/即xxx" 等编者解释
# 例: 候补：清代官制，通过科举或捐纳等途径取得官衔...听候委用。
# 例: 头钱：旧时提供赌博场所的人...
HISTORICAL_NOTE = re.compile(
    r'：(?:旧时|古时|清代|明代|宋代|唐代|汉代|语见|语出|指当时|即指|是指|通译|今译|这里|英语|日语|法语|德语)'
    r'[^\n]{0,300}?[。！？]'
)


def strip_editor_notes(p):
    p = WESTERN_PAREN.sub("", p)
    for _ in range(3):
        p = WESTERN_DOUBLE_NOTE.sub("", p)
        p = WESTERN_DOUBLE_NOTE_SHORT.sub("", p)
        p = NAME_NOTE.sub("", p)
        p = QUOTED_NOTE.sub("", p)
        p = HISTORICAL_NOTE.sub("。", p)  # 用句号替代，保持句子完整
    p = WESTERN_INLINE.sub("", p)
    p = DUP_CN.sub(r"\1", p)
    # 修复 "。X。" 这种孤立残尾（X 是 1-3 个字，通常是注释删除后留下的尾巴）
    p = re.sub(r"。([\u4e00-\u9fa5]{1,3})。", "。", p)
    p = re.sub(r"，{2,}", "，", p)
    p = re.sub(r"。{2,}", "。", p)
    p = re.sub(r"\s+", "", p)
    return p


def is_junk(line):
    for pat in JUNK_LINE_PATTERNS:
        if pat.search(line):
            return True
    return False


def clean_paragraph(p):
    p = p.lstrip("　 \t")
    p = EDITOR_NOTE.sub("", p)
    p = strip_editor_notes(p)
    return p.strip()


# ============ 解析 ============

def load_text():
    return SRC.read_text(encoding="utf-8-sig").replace("\r\n", "\n")


CHAP_PAT = re.compile(r"^第(\d+)章\s+([^\n]+)$", re.MULTILINE)


def parse_all_chapters(text):
    """返回 [(chap_num, title, body), ...] 按顺序"""
    matches = list(CHAP_PAT.finditer(text))
    chapters = []
    for i, m in enumerate(matches):
        num = int(m.group(1))
        title = m.group(2).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end]
        chapters.append((num, title, body))
    return chapters


def strip_part_suffix(title):
    """去掉 (1)(2) 等 part 标记，返回基础标题"""
    return re.sub(r"\s*[（(]\d+[）)]\s*$", "", title).strip()


def has_part_suffix(title):
    return bool(re.search(r"[（(]\d+[）)]\s*$", title))


def merge_parts(chapters):
    """
    将连续的同名 multi-part 章节合并。
    返回 [(first_chap_num, base_title, merged_body, [original_chap_nums]), ...]
    """
    merged = []
    i = 0
    while i < len(chapters):
        num, title, body = chapters[i]
        base = strip_part_suffix(title)
        # 收集所有连续同名 part
        bodies = [body]
        nums = [num]
        j = i + 1
        if has_part_suffix(title):
            while j < len(chapters):
                n2, t2, b2 = chapters[j]
                if has_part_suffix(t2) and strip_part_suffix(t2) == base:
                    bodies.append(b2)
                    nums.append(n2)
                    j += 1
                else:
                    break
        merged_body = "\n".join(bodies)
        merged.append((nums[0], base, merged_body, nums))
        i = j if j > i + 1 else i + 1
    return merged


def clean_body(body):
    paras = [clean_paragraph(p) for p in body.split("\n")]
    paras = [p for p in paras if p and not is_junk(p)]
    return paras


def slugify(title):
    """中文标题 → 简短英文 slug。这里用一个 hash + 序号策略：保留中文，仅去掉特殊字符。"""
    # 简单处理：去掉标点，保留中文和数字字母
    s = re.sub(r"[\s《》""''「」、，。！？：；·\(\)（）\[\]【】\-—]+", "_", title)
    s = s.strip("_")
    # 限制长度
    if len(s) > 30:
        s = s[:30]
    return s


# ============ 分类 ============

def section_for(chap_num):
    for lo, hi, slug, name in SECTIONS:
        if lo <= chap_num <= hi:
            return slug, name
    return None, None


# ============ 写出 ============

def write_work(out_dir, base_num, title, paras, original_nums, section_name):
    if not paras:
        return None
    meta = ""
    body_paras = paras
    if paras and (
        paras[0].startswith("本篇最初发表于")
        or "最初发表于" in paras[0][:30]
        or paras[0].startswith("《") and "最初发表于" in paras[0][:50]
    ):
        meta = paras[0]
        body_paras = paras[1:]
    if not body_paras:
        return None

    fn = f"{base_num:03d}_{slugify(title)}.md"
    out = out_dir / fn

    lines = [
        f"# {title}",
        "",
        f"_出自：{section_name}_",
        "",
    ]
    if meta:
        lines += [f"> {meta}", ""]
    for p in body_paras:
        lines.append(p)
        lines.append("")
    out.write_text("\n".join(lines), encoding="utf-8")

    word_count = sum(len(p) for p in body_paras)
    return {
        "filename": fn,
        "title": title,
        "section": section_name,
        "section_slug": out_dir.name,
        "chap_num": base_num,
        "original_nums": original_nums,
        "word_count": word_count,
        "first_line": body_paras[0][:60] if body_paras else "",
    }


def write_index(records):
    """写总索引"""
    by_section = OrderedDict()
    for r in records:
        by_section.setdefault((r["section_slug"], r["section"]), []).append(r)

    lines = [
        "# 鲁迅全集索引",
        "",
        f"共 **{len(records)}** 篇，按集分类。",
        "",
        "Claude 在用户没有指定篇目时，应根据问题主题在这个索引里挑选 1-3 篇相关作品阅读。",
        "若用户明确指定了篇目（如「用《狂人日记》和《我之节烈观》的方式」），优先读用户指定的。",
        "",
        "---",
        "",
    ]

    for (slug, name), items in by_section.items():
        lines.append(f"## {name}（{len(items)} 篇）")
        lines.append("")
        lines.append(f"目录：`{slug}/`")
        lines.append("")
        for r in items:
            preview = r["first_line"].replace("\n", " ")
            lines.append(f"- **{r['title']}** — `{r['filename']}` （约 {r['word_count']} 字）")
            if preview:
                lines.append(f"  > {preview}…")
        lines.append("")

    (OUT_ROOT / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    text = load_text()
    chapters = parse_all_chapters(text)
    print(f"原始章节数：{len(chapters)}")

    # 剔除第 1 章（编者前言）
    chapters = [c for c in chapters if c[0] != 1]
    print(f"剔除编者前言后：{len(chapters)}")

    merged = merge_parts(chapters)
    print(f"合并 multi-part 后：{len(merged)} 篇独立作品")

    # 清空旧目录
    if OUT_ROOT.exists():
        import shutil
        shutil.rmtree(OUT_ROOT)
    OUT_ROOT.mkdir(parents=True)

    records = []
    skipped = 0
    for base_num, base_title, body, orig_nums in merged:
        slug, name = section_for(base_num)
        if slug is None:
            print(f"  ✗ 第{base_num}章 无所属集：{base_title}")
            skipped += 1
            continue
        out_dir = OUT_ROOT / slug
        out_dir.mkdir(exist_ok=True)
        paras = clean_body(body)
        rec = write_work(out_dir, base_num, base_title, paras, orig_nums, name)
        if rec:
            records.append(rec)
        else:
            skipped += 1

    write_index(records)
    print(f"\n写出 {len(records)} 篇，跳过 {skipped} 篇")
    # 按集汇总
    from collections import Counter
    c = Counter(r["section"] for r in records)
    for k, v in c.items():
        print(f"  {k}: {v} 篇")


if __name__ == "__main__":
    main()
