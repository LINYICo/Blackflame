"""Check source-bound replacement plans against XML structure and text."""
from collections import Counter
import json

from lxml import etree
from publication import DC, LIMIT_XML, OPF, XHTML, parse_xml, require, xml_member


EDITABLE_METADATA = {
    f"{{{DC}}}{field}"
    for field in ("title", "creator", "language", "publisher", "description", "subject", "contributor")
}


def compare_xml(old, new, member, scope_error):
    # C14N cannot serialize unresolved EPUB 2 entities. In that case compare
    # the stricter XML serialization, keeping entity references intact.
    has_entities = any(next(tree.getroot().iter(etree.Entity), None) is not None for tree in (old, new))
    method = "xml" if has_entities else "c14n"
    require(etree.tostring(old, method=method) == etree.tostring(new, method=method),
            f"{scope_error}: {member}")
    # Canonical XML omits the document type declaration and its internal subset.
    if old.docinfo.doctype:
        for tree in (old, new):
            tree.getroot().clear()
        require(etree.tostring(old) == etree.tostring(new), f"Document type declaration changed: {member}")


def check_edit(member, before, after, is_package):
    old, new = parse_xml(before), parse_xml(after)
    for field in ("doctype", "encoding", "standalone", "xml_version"):
        require(getattr(old.docinfo, field) == getattr(new.docinfo, field),
                f"XML declaration or doctype changed: {member}")
    if is_package:
        modified = "meta[@property='dcterms:modified' and not(@refines)]"
        for tree in (old, new):
            for node in tree.xpath("/*/opf:metadata/*", namespaces={"opf": OPF}):
                if node.tag in EDITABLE_METADATA and len(node) == 0:
                    node.text = None
            for node in tree.xpath(f"/*/opf:metadata/opf:{modified}", namespaces={"opf": OPF}):
                node.text = None
        compare_xml(old, new, member, "OPF changes exceed metadata text edits")
        return

    old_root, new_root = old.getroot(), new.getroot()
    require(old_root.tag == new_root.tag == f"{{{XHTML}}}html", f"Invalid XHTML root: {member}")
    bodies = [tree.getroot().findall(f"{{{XHTML}}}body") for tree in (old, new)]
    require(all(len(matches) == 1 for matches in bodies), f"Expected one XHTML body: {member}")
    anchor_xpath = "//@id | //@xml:id | //x:a/@name"
    old_anchors, new_anchors = (
        Counter(tree.xpath(anchor_xpath, namespaces={"x": XHTML})) for tree in (old, new)
    )
    require(not (old_anchors - new_anchors), f"Existing anchor removed: {member}")
    for (body,) in bodies:
        body.text = None
        for child in list(body):
            body.remove(child)
    compare_xml(old, new, member, "XHTML changes outside body content")


def check_text_edits(member, before, after, edits):
    """Replay reviewed substitutions on individual XHTML body text nodes."""
    require(isinstance(edits, list) and edits, f"Expected text edits for {member}")
    expected = parse_xml(before)
    growth_budget = LIMIT_XML
    for edit in edits:
        require(isinstance(edit, dict) and edit.keys() == {"old", "new", "count"},
                f"Expected old, new and count in {member}")
        old, new, count = edit["old"], edit["new"], edit["count"]
        require(isinstance(old, str) and old and isinstance(new, str) and new != old
                and type(count) is int and count > 0, f"Invalid text substitution in {member}")
        matches = 0
        for value in expected.xpath("/x:html/x:body//text()", namespaces={"x": XHTML}):
            occurrences = value.count(old)
            if occurrences:
                matches += occurrences
                require(matches <= count, f"Unexpected text match count in {member}")
                growth_budget -= occurrences * max(0, len(new) - len(old))
                require(growth_budget >= 0, f"Text substitutions exceed XML size limit in {member}")
                field = "tail" if value.is_tail else "text"
                setattr(value.getparent(), field, value.replace(old, new))
        require(matches == count, f"Unexpected text match count in {member}")
    compare_xml(expected, parse_xml(after), member, "Replacement differs from reviewed text edits")


def unique_fields(pairs):
    fields = dict(pairs)
    require(len(fields) == len(pairs), "Duplicate key in replacement plan")
    return fields


def read_replacements(archive, book, plan_path, digest):
    plan = json.loads(plan_path.read_text(encoding="utf-8"), object_pairs_hook=unique_fields)
    require(isinstance(plan, dict) and plan.get("source_sha256") == digest, "Plan source SHA-256 differs")
    proposed = plan.get("replacements")
    require(isinstance(proposed, dict) and proposed, "Plan must contain replacements")
    require(len(book["packages"]) == 1, "Editing requires a single OPF package")
    require(not book["protection"], f"Protected publication: {', '.join(book['protection'])}")
    package = book["packages"][0]
    require(package["version"] in {"2.0", "3.0"}, "Editing supports EPUB 2.0 and 3.0 packages")
    documents = {
        item["member"] for item in package["manifest"]
        if item["member"] is not None and item["media_type"] == "application/xhtml+xml"
    }
    documents -= {item["member"] for item in package["manifest"] if "nav" in item["properties"]}
    text_edits = plan.get("text_edits", {})
    require(isinstance(text_edits, dict) and text_edits.keys() <= (documents & proposed.keys()),
            "Text edits must name replacement XHTML documents")
    allowed = documents | {package["member"]}
    replacements = {}
    for member, file in proposed.items():
        require(member in allowed and isinstance(file, str), f"Unsupported replacement: {member}")
        old = xml_member(archive, member)
        with (plan_path.parent / file).open("rb") as handle:
            new = handle.read(LIMIT_XML + 1)
        require(len(new) <= LIMIT_XML, f"Replacement exceeds XML size limit: {member}")
        require(new != old, f"Replacement has no byte changes: {member}")
        check_edit(member, old, new, member == package["member"])
        if member in text_edits:
            check_text_edits(member, old, new, text_edits[member])
        replacements[member] = new
    return replacements
