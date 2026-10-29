# -*- coding: utf-8 -*-
"""批量改名核心逻辑。

职责：
1. 解析目标模板，例如 "{学号}-{姓名}-第4次作业"；
2. 从任意格式的旧文件名里识别出 学号 / 姓名 / 作业 / 内容；
3. 按模板生成新文件名，并检查重名、非法字符等风险；
4. 执行改名（两阶段改名，避免互相占位死锁）与撤销。

对外接口见文件末尾的 build_plan / apply_plan / undo_log。
"""
from __future__ import annotations

import csv
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------- 常量

DEFAULT_TEMPLATE = "{学号}-{姓名}-{作业}"
PLACEHOLDERS = ("学号", "姓名", "作业", "内容")

# 常见单字姓（覆盖绝大多数学生）
SURNAMES_SINGLE = set(
    "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜戚谢邹喻柏水窦章云苏潘葛"
    "奚范彭郎鲁韦昌马苗凤花方俞任袁柳酆鲍史唐费廉岑薛雷贺倪汤滕殷罗毕郝邬安常乐于时傅皮卞齐康"
    "伍余元卜顾孟平黄和穆萧尹姚邵湛汪祁毛禹狄米贝明臧计伏成戴谈宋茅庞熊纪舒屈项祝董梁杜阮蓝闵"
    "席季麻强贾路娄危江童颜郭梅盛林刁钟徐邱骆高夏蔡田樊胡凌霍虞万支柯昝管卢莫经房裘缪干解应宗"
    "丁宣贲邓郁单杭洪包诸左石崔吉钮龚程嵇邢滑裴陆荣翁荀羊惠甄曲家封芮羿储靳汲邴糜松井段富巫乌"
    "焦巴弓牧隗山谷车侯宓蓬全郗班仰秋仲伊宫宁仇栾暴甘钭厉戎祖武符刘景詹束龙叶幸司韶郜黎蓟薄印"
    "宿白怀蒲邰从鄂索咸籍赖卓蔺屠蒙池乔阴胥能苍双闻莘党翟谭贡劳逄姬申扶堵冉宰郦雍却璩桑桂濮牛"
    "寿通边扈燕冀郏浦尚农温别庄晏柴瞿阎充慕连茹习宦艾鱼容向古易慎戈廖庾终暨居衡步都耿满弘匡国"
    "文寇广禄阙东欧殳沃利蔚越夔隆师巩厍聂晁勾敖融冷訾辛阚那简饶空曾毋沙乜养鞠须丰巢关蒯相查后"
    "荆红游竺权逯盖益桓公"
    # 百家姓之外、现实中很常见的姓
    "肖付闫覃粟邝冼麦练招植佘禤银门"
)

# 常见复姓
COMPOUND_SURNAMES = (
    "欧阳", "司马", "上官", "诸葛", "东方", "皇甫", "尉迟", "公孙", "慕容", "长孙",
    "宇文", "司徒", "鲜于", "独孤", "南宫", "令狐", "申屠", "端木", "拓跋", "轩辕",
    "夏侯", "闻人", "万俟", "呼延", "赫连", "澹台", "公冶", "宗政", "太史", "仲孙",
    "钟离", "闾丘", "亓官", "司寇", "左丘", "东郭", "西门", "第五",
)

# 姓名里不该出现的字（避免把"第""次""作业"等误当名字）
# 注意：新、正、文这类字在真实姓名里很常见（朱雅新、李正阳），不能放进来
BAD_NAME_CHARS = set(
    "第次作业实验报告上机题卷册章节课练测考论文档表格截图姓名学号期周月日版副本终结稿修改定旧"
    "班组成科系院级"
)

# 课程/作业名里常见的词，用来避免把人名识别成课程名（只在没有常见姓时用来兜底）
COURSE_WORDS = (
    "数据", "结构", "原理", "设计", "导论", "概论", "基础", "编程", "程序", "系统",
    "网络", "算法", "模型", "方法", "技术", "应用", "管理", "经济", "数学", "物理",
    "化学", "英语", "语文", "历史", "地理", "生物", "政治", "体育", "艺术", "音乐",
    "美术", "教程", "实验", "报告", "作业", "笔记", "讲义", "复习", "考试", "期末",
    "期中", "课程", "上机", "练习", "测验", "考核", "答案", "解析", "总结", "文档",
)


# 出现在名字后面，说明名字到此为止（多半是作业信息）
CONTENT_KEYWORDS = (
    "第", "作", "实", "上", "报", "期", "练", "测", "考", "论", "课", "卷", "册",
    "章", "节", "次", "学", "数", "程", "导", "基", "文", "图", "表", "设", "计",
    "项", "目", "小", "大", "末", "补", "重", "班", "组", "年", "级",
)

# 分隔符（识别时视作边界，不进入任何字段）
SEP_CHARS = set(
    "-_—–·.,;:()（）[]【】{}<>《》\"'`、，。；：|\\/ \t　~!！?？+&@#%^*=“”‘’"
)

ILLEGAL_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

STATUS_RENAME = "待改名"
STATUS_SAME = "已符合"
STATUS_CONFLICT = "重名冲突"
STATUS_UNPARSED = "无法识别"
STATUS_EXISTS = "已存在同名"
STATUS_ILLEGAL = "名称非法"

_CN_DIGITS = "零一二三四五六七八九"
_CN_NUM = r"(?:\d{1,3}|[零〇一二三四五六七八九十两]{1,3})"
_ACT = r"(?:实验报告|作业|上机|实验|练习|测验|考核|报告|课设|编程)"


class TemplateError(ValueError):
    """模板写法有误。"""


class MissingPart(Exception):
    """旧文件名里缺少模板要求的字段。"""

    def __init__(self, part: str):
        super().__init__(f"缺少{part}")
        self.part = part


# ---------------------------------------------------------------- 模板

def split_template(template: str) -> list[tuple[str, str]]:
    """把模板拆成 [("lit", "-"), ("ph", "学号"), ...]。

    只认识 {学号}/{姓名}/{作业}/{内容}，其余花括号内容原样当字面量。
    """
    if not template or not template.strip():
        raise TemplateError("模板不能为空")
    segs: list[tuple[str, str]] = []
    for chunk in re.split(r"(\{[^{}]*\})", template):
        if not chunk:
            continue
        m = re.fullmatch(r"\{([^{}]*)\}", chunk)
        if m:
            key = m.group(1).strip()
            if key not in PLACEHOLDERS:
                raise TemplateError(
                    f"模板里有不认识的占位符 {{{key}}}，只能用："
                    + "、".join("{" + p + "}" for p in PLACEHOLDERS)
                )
            segs.append(("ph", key))
        else:
            segs.append(("lit", chunk))
    if not any(kind == "ph" for kind, _ in segs):
        raise TemplateError(
            "模板至少要包含一个占位符，例如 {学号}-{姓名}-第4次作业"
        )
    return segs


# ---------------------------------------------------------------- 基础工具

def _is_cjk(ch: str) -> bool:
    return "\u4e00" <= ch <= "\u9fff"


def _to_halfwidth(text: str) -> str:
    """全角数字/字母转半角，全角括号转半角，便于统一识别。"""
    out = []
    for ch in text:
        code = ord(ch)
        if code == 0x3000:
            out.append(" ")
        elif 0xFF01 <= code <= 0xFF5E:
            out.append(chr(code - 0xFEE0))
        else:
            out.append(ch)
    return "".join(out)


def cn_to_int(text: str) -> int:
    """中文数字转整数：四 -> 4，十二 -> 12，二十 -> 20。"""
    text = text.strip()
    if not text:
        raise ValueError("空数字")
    if text.isdigit():
        return int(text)
    text = text.replace("〇", "零").replace("两", "二")
    if text == "十":
        return 10
    if "十" in text:
        left, _, right = text.partition("十")
        tens = _CN_DIGITS.index(left) if left else 1
        ones = _CN_DIGITS.index(right) if right else 0
        return tens * 10 + ones
    value = 0
    for ch in text:
        value = value * 10 + _CN_DIGITS.index(ch)
    return value


def _strip_seps(text: str) -> str:
    return text.strip("".join(SEP_CHARS))


_ASSIGN_PATTERNS = [
    # 第4次作业 / 第四次实验
    (re.compile(rf"第\s*({_CN_NUM})\s*次\s*({_ACT})"), "ci"),
    # 作业4 / 实验三
    (re.compile(rf"({_ACT})\s*第?\s*({_CN_NUM})(?!\d)"), "direct"),
    # 第4次（没写是什么）
    (re.compile(rf"第\s*({_CN_NUM})\s*次"), "ci_only"),
]


def extract_assignment(text: str) -> tuple[str, tuple[int, int]] | None:
    """识别"作业"信息，返回 (规范写法, (起, 止))。"""
    for pattern, kind in _ASSIGN_PATTERNS:
        m = pattern.search(text)
        if not m:
            continue
        if kind == "ci":
            num, act = m.group(1), m.group(2)
            try:
                n = cn_to_int(num)
            except ValueError:
                continue
            return f"第{n}次{act}", m.span()
        if kind == "direct":
            act, num = m.group(1), m.group(2)
            try:
                n = cn_to_int(num)
            except ValueError:
                continue
            return f"{act}{n}", m.span()
        try:
            n = cn_to_int(m.group(1))
        except ValueError:
            continue
        return f"第{n}次", m.span()
    return None


ID_RE = re.compile(r"(?<!\d)(\d{6,})(?!\d)")


def extract_id(text: str, min_len: int = 6) -> tuple[str, tuple[int, int]] | None:
    """识别学号：取最长的连续数字串（默认至少 6 位）。"""
    pattern = ID_RE if min_len >= 6 else re.compile(rf"(?<!\d)(\d{{{min_len},}})(?!\d)")
    found = list(pattern.finditer(text))
    if not found:
        return None
    best = max(found, key=lambda m: (len(m.group(1)), -m.start()))
    return best.group(1), best.span()


def find_name(text: str) -> tuple[str, tuple[int, int], float] | None:
    """在文本里找最可能的姓名，返回 (姓名, (起, 止), 置信分)。"""
    best: tuple[float, int, int, str] | None = None
    n = len(text)
    for i in range(n):
        options: list[tuple[str, int]] = []
        for surname in COMPOUND_SURNAMES:
            if text.startswith(surname, i):
                options.append((surname, len(surname)))
        if text[i] in SURNAMES_SINGLE:
            options.append((text[i], 1))
        for surname, slen in options:
            for extra in (1, 2):
                j = i + slen + extra
                if j > n:
                    continue
                given = text[i + slen:j]
                if not all(_is_cjk(c) and c not in BAD_NAME_CHARS for c in given):
                    continue
                score = 0.0
                prev = text[i - 1] if i else ""
                nxt = text[j] if j < n else ""
                if not prev or prev in SEP_CHARS or not (prev.isalnum() or _is_cjk(prev)):
                    score += 3.0
                elif _is_cjk(prev):
                    # 姓前面还挤着汉字，多半是从更长的名字里截出来的（巴桑嘉布 → 桑嘉布）
                    score -= 2.0
                if not nxt:
                    score += 3.0
                elif nxt in SEP_CHARS:
                    score += 3.0
                elif any(nxt.startswith(k) for k in CONTENT_KEYWORDS):
                    score += 2.0
                elif _is_cjk(nxt):
                    # 名字后面还紧跟着汉字，说明多半把词切断了，例如"肖涵郡"只取到"肖涵"
                    score -= 1.5
                # 两字名更常见，三字名只有在边界更干净时才胜出
                score += 1.0 if extra == 1 else 0.6
                cand = (score, -i, -extra, surname + given)
                if best is None or cand[:3] > best[:3]:
                    best = cand
                    best_span = (i, j)
                    best_name = surname + given
    if best is None:
        return None
    return best_name, best_span, best[0]


def _split_pieces(text: str, start: int, end: int) -> list[tuple[int, int]]:
    """把一段连续汉字按"作业/报告"这类关键字切开，返回纯人名的候选片段。"""
    pieces: list[tuple[int, int]] = []
    cur: list[int] | None = None
    for i in range(start, end):
        if text[i] in BAD_NAME_CHARS:
            if cur is not None:
                pieces.append((cur[0], cur[1]))
                cur = None
        else:
            if cur is None:
                cur = [i, i + 1]
            else:
                cur[1] = i + 1
    if cur is not None:
        pieces.append((cur[0], cur[1]))
    return pieces


def _cjk_pieces(text: str) -> list[tuple[int, int]]:
    pieces: list[tuple[int, int]] = []
    start = None
    for i in range(len(text) + 1):
        is_cjk = i < len(text) and _is_cjk(text[i])
        if is_cjk and start is None:
            start = i
        elif not is_cjk and start is not None:
            pieces.extend(_split_pieces(text, start, i))
            start = None
    return pieces


def find_name_fallback(text: str, id_span: tuple[int, int] | None) -> tuple[str, tuple[int, int]] | None:
    """少见姓氏（少数民族姓名等）兜底：取紧挨学号的一段 2~5 字纯汉字。

    只在常见姓完全匹配不上时使用，且要求与学号相邻，尽量减少误判。
    """
    if not id_span:
        return None
    best: tuple[float, int, str, tuple[int, int]] | None = None
    for start, end in _cjk_pieces(text):
        seg = text[start:end]
        if not 2 <= len(seg) <= 5:
            continue
        if any(word in seg for word in COURSE_WORDS):
            continue
        gap_before = id_span[0] - end
        gap_after = start - id_span[1]
        if not ((0 <= gap_before <= 2) or (0 <= gap_after <= 2)):
            continue
        score = 6 - abs(len(seg) - 3)  # 三个字优先，其次是 2/4 字
        candidate = (score, -start, seg, (start, end))
        if best is None or candidate[:2] > best[:2]:
            best = candidate
    if best is None:
        return None
    return best[2], best[3]


def parse_name(stem: str, id_min_len: int = 6) -> dict[str, str]:
    """拆解旧文件名主干（不含扩展名），返回识别到的字段。"""
    text = _to_halfwidth(stem)
    parts: dict[str, str] = {}
    spans: list[tuple[int, int]] = []
    id_span: tuple[int, int] | None = None

    found = extract_id(text, id_min_len)
    if found:
        parts["学号"], span = found
        spans.append(span)
        id_span = span

    found_assign = extract_assignment(text)
    if found_assign:
        parts["作业"], span = found_assign
        spans.append(span)

    # 抹掉已识别片段（换成空格，避免影响相邻判断），再找人名
    masked = list(text)
    for start, end in spans:
        for k in range(start, end):
            masked[k] = " "
    masked_text = "".join(masked)

    found_name = find_name(masked_text)
    name_weak = found_name is not None and found_name[2] < 3.0
    if found_name is None or name_weak:
        # 常见姓匹配不上、或只是在长名字里截了一段（巴桑嘉布 → 桑嘉布）时，按位置兜底
        alt = find_name_fallback(masked_text, id_span)
        if alt is not None:
            found_name = (alt[0], alt[1], 0.0)
        elif name_weak:
            # 弱匹配又找不到更完整的名字，多半是把课程名切了一半（计算机组成原理 → 计算）
            found_name = None
    if found_name:
        parts["姓名"], span = found_name[0], found_name[1]
        spans.append(span)

    # 内容 = 去掉已知字段后剩下的文字
    rest = list(text)
    for start, end in sorted(spans, reverse=True):
        del rest[start:end]
    content = "".join(rest)
    content = _strip_seps(content)
    content = re.sub(r"[\s　]+", "", content)
    content = re.sub(f"[{re.escape(''.join(SEP_CHARS))}]+", "-", content)
    content = _strip_seps(content)
    if content:
        parts["内容"] = content

    return parts


# ---------------------------------------------------------------- 组装

def sanitize_filename(name: str) -> str:
    cleaned = ILLEGAL_CHARS.sub("", name)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" .")
    return cleaned


def build_new_name(parts: dict[str, str], segs: list[tuple[str, str]]) -> str:
    """按模板顺序拼出新文件名主干；缺字段抛 MissingPart。"""
    out: list[str] = []
    for kind, value in segs:
        if kind == "lit":
            out.append(value)
            continue
        got = parts.get(value, "")
        if not got:
            raise MissingPart(value)
        out.append(got)
    name = "".join(out)
    name = re.sub(r"-{2,}", "-", name)
    name = re.sub(r"_{2,}", "_", name)
    name = sanitize_filename(name)
    return name


# ---------------------------------------------------------------- 计划

@dataclass
class Entry:
    path: Path
    old_name: str
    new_name: str
    status: str
    reason: str = ""
    parts: dict[str, str] | None = None

    @property
    def needs_action(self) -> bool:
        return self.status == STATUS_RENAME


@dataclass
class Plan:
    folder: Path
    template: str
    entries: list[Entry]

    @property
    def to_rename(self) -> list[Entry]:
        return [e for e in self.entries if e.status == STATUS_RENAME]

    def count(self, status: str) -> int:
        return sum(1 for e in self.entries if e.status == status)


def collect_files(folder: Path, recursive: bool) -> list[Path]:
    if recursive:
        files = [p for p in folder.rglob("*") if p.is_file()]
    else:
        files = [p for p in folder.iterdir() if p.is_file()]
    # 跳过本工具自己的日志目录与常见临时文件
    files = [
        p for p in files
        if p.suffix.lower() not in (".tmp", ".log")
        and not p.name.startswith("~$")
        and p.name != "改名日志.csv"
    ]
    return sorted(files, key=lambda p: str(p).lower())


def build_plan(
    folder: Path | str,
    template: str = DEFAULT_TEMPLATE,
    recursive: bool = False,
    id_min_len: int = 6,
) -> Plan:
    folder = Path(folder)
    if not folder.is_dir():
        raise FileNotFoundError(f"文件夹不存在：{folder}")
    segs = split_template(template)
    entries: list[Entry] = []
    for path in collect_files(folder, recursive):
        stem, ext = os.path.splitext(path.name)
        try:
            parts = parse_name(stem, id_min_len)
        except Exception as exc:  # 单文件异常不影响整体
            entries.append(Entry(path, path.name, "", STATUS_UNPARSED, f"解析出错：{exc}"))
            continue
        try:
            new_stem = build_new_name(parts, segs)
        except MissingPart as exc:
            entries.append(Entry(path, path.name, "", STATUS_UNPARSED, f"文件名里找不到{exc.part}", parts))
            continue
        except Exception as exc:
            entries.append(Entry(path, path.name, "", STATUS_UNPARSED, f"组装出错：{exc}", parts))
            continue

        if not new_stem:
            entries.append(Entry(path, path.name, "", STATUS_UNPARSED, "生成的名字为空", parts))
            continue
        new_name = new_stem + ext
        base = new_stem.split(".")[0].upper()
        if base in WINDOWS_RESERVED:
            entries.append(Entry(path, path.name, new_name, STATUS_ILLEGAL, "是 Windows 保留名", parts))
            continue
        if len(new_name) > 255:
            entries.append(Entry(path, path.name, new_name, STATUS_ILLEGAL, "名字过长", parts))
            continue
        if new_name == path.name:
            entries.append(Entry(path, path.name, new_name, STATUS_SAME, "已经是目标格式", parts))
            continue
        entries.append(Entry(path, path.name, new_name, STATUS_RENAME, "", parts))

    # 冲突检查：计划内重名 + 磁盘上已存在
    seen: dict[tuple[str, str], list[Entry]] = {}
    for entry in entries:
        if entry.status != STATUS_RENAME:
            continue
        key = (str(entry.path.parent).lower(), entry.new_name.lower())
        seen.setdefault(key, []).append(entry)
    for key, group in seen.items():
        if len(group) > 1:
            for entry in group:
                entry.status = STATUS_CONFLICT
                entry.reason = f"有 {len(group)} 个文件会改成同一个名字"
            continue
        entry = group[0]
        target = entry.path.parent / entry.new_name
        if target.exists() and target.name.lower() != entry.old_name.lower():
            entry.status = STATUS_EXISTS
            entry.reason = "目标文件已存在"

    return Plan(folder=folder, template=template, entries=entries)


# ---------------------------------------------------------------- 执行

def default_log_dir() -> Path:
    """日志目录：装在系统里时放到用户目录，开发时放项目下；都不写程序目录。"""
    import sys

    if getattr(sys, "frozen", False):
        local = Path(os.environ.get("LOCALAPPDATA") or Path.home())
        bases = (local / "批量改名工具" / "改名日志", Path.home() / "改名日志")
    else:
        bases = (Path(__file__).resolve().parent.parent / "改名日志", Path.home() / "改名日志")
    for candidate in bases:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            probe = candidate / ".write_test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            return candidate
        except OSError:
            continue
    return Path.cwd()


@dataclass
class ApplyResult:
    renamed: int
    failed: list[tuple[str, str]]
    log_path: Path | None


def apply_plan(plan: Plan, log_dir: Path | str | None = None) -> ApplyResult:
    """执行改名。先用临时名重命名，再改成目标名，避免互相占位。"""
    todo = plan.to_rename
    if not todo:
        return ApplyResult(0, [], None)

    log_dir = Path(log_dir) if log_dir else default_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = log_dir / f"改名日志-{stamp}.csv"

    staged: list[tuple[Entry, Path]] = []
    failed: list[tuple[str, str]] = []
    for entry in todo:
        tmp = entry.path.with_name(f"__renaming__{uuid.uuid4().hex[:8]}{entry.path.suffix}")
        try:
            entry.path.rename(tmp)
            staged.append((entry, tmp))
        except OSError as exc:
            failed.append((entry.old_name, f"重命名失败：{exc}"))

    renamed = 0
    rows: list[tuple[str, str, str, str, str]] = []
    for entry, tmp in staged:
        target = entry.path.with_name(entry.new_name)
        try:
            tmp.rename(target)
            renamed += 1
            rows.append((
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                str(entry.path.parent),
                entry.old_name,
                entry.new_name,
                "成功",
            ))
        except OSError as exc:
            # 回滚这一步，保持原名
            try:
                tmp.rename(entry.path)
            except OSError:
                pass
            failed.append((entry.old_name, f"改成新名字失败：{exc}"))

    with open(log_path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["时间", "目录", "原文件名", "新文件名", "结果"])
        writer.writerows(rows)

    return ApplyResult(renamed, failed, log_path)


def undo_log(log_path: Path | str) -> tuple[int, list[tuple[str, str]]]:
    """按日志撤销：把"新文件名"改回"原文件名"。"""
    log_path = Path(log_path)
    restored = 0
    failed: list[tuple[str, str]] = []
    with open(log_path, "r", encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    for row in reversed(rows):
        if row.get("结果") != "成功":
            continue
        folder = Path(row["目录"])
        new_path = folder / row["新文件名"]
        old_path = folder / row["原文件名"]
        if not new_path.exists():
            failed.append((row["新文件名"], "文件已不存在"))
            continue
        if old_path.exists():
            failed.append((row["原文件名"], "原文件名已被占用"))
            continue
        try:
            new_path.rename(old_path)
            restored += 1
        except OSError as exc:
            failed.append((row["新文件名"], str(exc)))
    return restored, failed
