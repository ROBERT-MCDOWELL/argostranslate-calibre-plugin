import copy
import re
from typing import NamedTuple, Optional
XML_LANG = '{http://www.w3.org/XML/1998/namespace}lang'
LETTER_RE = re.compile(r'[^\W\d_]')
BLOCK_TAGS = frozenset(['address', 'article', 'aside', 'blockquote', 'body', 'caption', 'center', 'dd', 'details', 'dialog', 'div', 'dl', 'dt', 'fieldset', 'figcaption', 'figure', 'footer', 'form', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'header', 'hgroup', 'hr', 'li', 'main', 'nav', 'ol', 'p', 'section', 'summary', 'table', 'tbody', 'td', 'tfoot', 'th', 'thead', 'tr', 'ul'])
SIBLING_TAGS = frozenset(['blockquote', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p'])
INNER_TAGS = frozenset(['caption', 'dd', 'dt', 'figcaption', 'li', 'td', 'th'])
PARA_TAGS = SIBLING_TAGS | INNER_TAGS
BREAK_TAGS = frozenset(['audio', 'br', 'iframe', 'img', 'input', 'object', 'video', 'wbr'])
SKIP_TAGS = frozenset(['code', 'head', 'kbd', 'math', 'pre', 'rp', 'rt', 'samp', 'script', 'style', 'sub', 'sup', 'svg', 'textarea', 'var'])
MEDIA_TAGS = frozenset(['audio', 'iframe', 'img', 'object', 'svg', 'video'])
class Segment(NamedTuple):
    run:list
    lead:str
    core:str
    trail:str
def local_name(el)->str:
    return el.tag.rpartition('}')[2] if isinstance(el.tag, str) else ''
def namespace(el)->str:
    return el.tag[:el.tag.index('}') + 1] if el.tag.startswith('{') else ''
def is_excluded(el)->bool:
    tag = local_name(el)
    return not tag or tag in SKIP_TAGS or el.get('translate') == 'no' or 'notranslate' in (el.get('class') or '').split()
def is_break(el)->bool:
    tag = local_name(el)
    return tag in BREAK_TAGS or (tag == 'a' and el.get('href') is not None)
def has_letters(text:str)->bool:
    return LETTER_RE.search(text) is not None
def normalize(text:str)->str:
    return ' '.join(text.split())
def block_roots(body)->list:
    roots:list = []
    def visit(el)->None:
        if is_excluded(el):
            return
        if local_name(el) in BLOCK_TAGS:
            roots.append(el)
        for child in el:
            visit(child)
    visit(body)
    return roots
def collect_runs(root)->list:
    runs:list = [[]]
    def cut()->None:
        if runs[-1]:
            runs.append([])
    def walk(el)->None:
        if el.text:
            runs[-1].append((el, 'text'))
        for child in el:
            if is_excluded(child) or local_name(child) in BLOCK_TAGS:
                cut()
            elif is_break(child):
                cut()
                walk(child)
                cut()
            else:
                walk(child)
            if child.tail:
                runs[-1].append((child, 'tail'))
    walk(root)
    return [run for run in runs if run]
def make_segments(root)->list:
    segments:list = []
    for run in collect_runs(root):
        text = ''.join(getattr(node, attr) or '' for node, attr in run)
        core = normalize(text)
        if has_letters(core):
            segments.append(Segment(run, text[:len(text) - len(text.lstrip())], core, text[len(text.rstrip()):]))
    return segments
def is_leaf(el)->bool:
    return not any(local_name(node) in BLOCK_TAGS for node in el.iterdescendants())
def drop_keep_tail(el)->None:
    parent = el.getparent()
    if parent is None:
        return
    if el.tail:
        prev = el.getprevious()
        if prev is not None:
            prev.tail = (prev.tail or '') + el.tail
        else:
            parent.text = (parent.text or '') + el.tail
    parent.remove(el)
def add_translation_node(el, dst:str):
    clone = copy.deepcopy(el)
    for node in list(clone.iter()):
        if local_name(node) in MEDIA_TAGS:
            drop_keep_tail(node)
    for node in clone.iter():
        if isinstance(node.tag, str):
            node.attrib.pop('id', None)
    if local_name(el) in INNER_TAGS:
        clone.tag = namespace(el) + 'div'
        clone.attrib.clear()
        clone.set('class', 'argos-translation')
        clone.tail = None
        el.append(clone)
    else:
        clone.set('class', ' '.join(filter(None, [clone.get('class'), 'argos-translation'])))
        clone.tail = el.tail
        el.tail = None
        el.addnext(clone)
    clone.set('lang', dst)
    clone.set(XML_LANG, dst)
    return clone
def retag_language(root, src:str, dst:str)->None:
    for node in root.iter():
        if not isinstance(node.tag, str):
            continue
        for key in ('lang', XML_LANG):
            value = node.get(key)
            if value and value.split('-')[0].lower() == src:
                node.set(key, dst)
    root.set('lang', dst)
    root.set(XML_LANG, dst)
def prepare_document(root, mode:str, src:str, dst:str)->list:
    body = next((child for child in root if local_name(child) == 'body'), None)
    if body is None:
        return []
    if mode != 'bilingual':
        retag_language(root, src, dst)
        return [segment for el in block_roots(body) for segment in make_segments(el)]
    segments:list = []
    for el in block_roots(body):
        if local_name(el) in PARA_TAGS and is_leaf(el) and make_segments(el):
            segments.extend(make_segments(add_translation_node(el, dst)))
    return segments
def apply_segment(segment:Segment, translated:Optional[str])->None:
    if not translated:
        return
    node, attr = segment.run[0]
    setattr(node, attr, segment.lead + translated + segment.trail)
    for node, attr in segment.run[1:]:
        setattr(node, attr, '')
