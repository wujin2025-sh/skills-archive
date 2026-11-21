#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""docx2md.py — ba-to-dev-ailink 技能工具：docx -> md 高保真转换。
完整保留：标题层级与章节编号（解析 Word 自动多级编号）、merge 感知表格、
图片全部以 base64 内嵌（data:image/...;base64,），md 自包含、任意渲染器(含 Obsidian)可显示。

用法：python docx2md.py <in.docx> <out.md>
"""
import sys, os, re, base64, zipfile
from docx import Document
from docx.oxml.ns import qn
from lxml import etree

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
A = '{http://schemas.openxmlformats.org/drawingml/2006/main}'
R = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
MIME = {'png':'image/png','jpg':'image/jpeg','jpeg':'image/jpeg','emf':'image/x-emf',
        'wmf':'image/x-wmf','gif':'image/gif','bmp':'image/bmp','tiff':'image/tiff'}

CN = ['〇','一','二','三','四','五','六','七','八','九','十']
def cn_num(n):
    if n <= 0: return ''
    if n <= 10: return CN[n]
    if n < 20: return '十' + (CN[n-10] if n > 10 else '')
    return str(n)

def to_roman(n):
    vals = [(1000,'M'),(900,'CM'),(500,'D'),(400,'CD'),(100,'C'),(90,'XC'),
            (50,'L'),(40,'XL'),(10,'X'),(9,'IX'),(5,'V'),(4,'IV'),(1,'I')]
    out=''
    for v,s in vals:
        while n >= v: out += s; n -= v
    return out

def format_num(fmt, n):
    f = (fmt or 'decimal').lower()
    if f in ('chinesecounting','chineselower'): return cn_num(n)
    if f == 'lowerletter': return chr(96+n)
    if f == 'upperletter': return chr(64+n)
    if f in ('lowerroman','upperroman'):
        r = to_roman(n); return r.lower() if f=='lowerroman' else r
    return str(n)

class NumState:
    def __init__(self, numbering_root):
        self.chunk = numbering_root
        self.counters = {}; self._formats = {}; self._texts = {}
        self._init()
    def _init(self):
        ns = self.chunk
        if ns is None: return
        num2abs = {}
        for num in ns.findall(W+'num'):
            nid = num.get(W+'numId'); ab = num.find(W+'abstractNumId')
            if ab is not None: num2abs[nid] = ab.get(W+'val')
        for numid, abid in num2abs.items():
            for ab in ns.findall(W+'abstractNum'):
                if ab.get(W+'abstractNumId') != abid: continue
                for lvl in ab.findall(W+'lvl'):
                    ilvl = int(lvl.get(W+'ilvl') or 0)
                    fmt = lvl.find(W+'numFmt'); txt = lvl.find(W+'lvlText')
                    self._formats[(numid,ilvl)] = fmt.get(W+'val') if fmt is not None else 'decimal'
                    self._texts[(numid,ilvl)] = txt.get(W+'val') if txt is not None else '%1.'
                break
    def next(self, numid, ilvl):
        if ilvl == 0:
            self.counters[(numid,ilvl)] = self.counters.get((numid,ilvl),0)+1
            for k in list(self.counters):
                if k[0]==numid and k[1]>ilvl: del self.counters[k]
        else:
            self.counters[(numid,ilvl)] = self.counters.get((numid,ilvl),0)+1
        nums = [self.counters.get((numid,l), (1 if l==ilvl else 1)) for l in range(0,ilvl+1)]
        fmt = self._formats.get((numid,ilvl),'decimal')
        pat = self._texts.get((numid,ilvl),'%1.')
        def repl(m):
            idx = int(m.group(1))-1
            if idx < len(nums):
                return format_num(fmt if idx==len(nums)-1 else self._formats.get((numid,idx),'decimal'), nums[idx])
            return '?'
        return re.sub(r'%(1|[1-9])', repl, pat)

def heading_level(style_name):
    mm = re.match(r'(?i)^heading\s*(\d+)$', style_name or '') or re.match(r'(?i)^标题\s*(\d+)$', style_name or '')
    return int(mm.group(1)) if mm else 0

def get_rids(p_el):
    out = []
    for blip in p_el.findall('.//'+A+'blip'):
        e = blip.get(R+'embed')
        if e: out.append(e)
    return out

def data_uri(blob, fname):
    ext = os.path.splitext(fname)[1].lower().lstrip('.') or 'png'
    return f"data:{MIME.get(ext,'image/png')};base64,{base64.b64encode(blob).decode('ascii')}"

def render_table(tbl):
    trs = tbl._tbl.findall(W+'tr')
    rows = []
    for tr in trs:
        cells = []
        for tc in tr.findall(W+'tc'):
            pr = tc.find(W+'tcPr'); span = 1; vm = None
            if pr is not None:
                g = pr.find(W+'gridSpan')
                if g is not None: span = int(g.get(W+'val'))
                v = pr.find(W+'vMerge')
                if v is not None: vm = 'cont' if v.get(W+'val') is None else 'start'
            text = " ".join("".join(n.text or "" for n in p.findall('.//'+W+'t')) for p in tc.findall(W+'p')).strip()
            if vm == 'cont':
                cells.append("")
            else:
                cells.append(text)
            for _ in range(1, span):
                cells.append("")
        rows.append(cells)
    if not rows: return ""
    ncols = max(len(r) for r in rows)
    rows = [r + [""]*(ncols-len(r)) for r in rows]
    rs = ["| " + " | ".join(c.replace("|","\\|").replace("\n"," ") for c in r) + " |" for r in rows]
    return "\n".join(rs)

def convert(src, out):
    doc = Document(src)
    numbering = None
    try:
        z = zipfile.ZipFile(src)
        if 'word/numbering.xml' in z.namelist():
            numbering = etree.fromstring(z.read('word/numbering.xml'))
        z.close()
    except Exception:
        pass
    num = NumState(numbering)
    body = doc.element.body
    seen = 0
    lines = []
    for child in body.iterchildren():
        tag = child.tag
        if tag == qn('w:p'):
            para = __import__('docx.text.paragraph', fromlist=['Paragraph']).Paragraph(child, doc)
            style = para.style.name if para.style else ''
            h = heading_level(style)
            txt = para.text.rstrip()
            prefix = ''
            npr = child.find('.//'+W+'numPr')
            if npr is not None:
                nid = npr.find(W+'numId'); ilv = npr.find(W+'ilvl')
                numid = nid.get(W+'val') if nid is not None else None
                ilvl = int(ilv.get(W+'val')) if ilv is not None else 0
                if numid is not None and numid != '0':
                    prefix = num.next(numid, ilvl)
            imgs = []
            for rid in get_rids(child):
                rel = doc.part.rels[rid]
                P = rel.target_part
                blob = P.blob
                fname = str(P.partname).split('/')[-1]
                seen += 1
                imgs.append(f"![图{seen}]({data_uri(blob, fname)})")
            img_md = "\n\n".join(imgs)
            if h >= 1:
                lines.append("#"*min(h,4) + " " + ('%s %s' % (prefix, txt) if prefix else txt))
            elif txt or img_md:
                parts = []
                if txt: parts.append(f"- **{prefix}** {txt}" if prefix else txt)
                if img_md: parts.append(img_md)
                lines.append("\n\n".join(parts))
        elif tag == qn('w:tbl'):
            m = render_table(__import__('docx.table', fromlist=['Table']).Table(child, doc))
            if m: lines.append(m)
    open(out, 'w', encoding='utf-8').write("\n\n".join(lines).strip() + "\n")
    print(f"OK -> {os.path.basename(out)} | embedded images: {seen} | size={os.path.getsize(out)//1024}KB")

if __name__ == '__main__':
    convert(sys.argv[1], sys.argv[2])