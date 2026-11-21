"""Read EPUB containers, inventory package documents and hash archive members."""
from copy import copy
from hashlib import file_digest, sha256
from io import BytesIO
import posixpath
import re
import stat
import struct
from urllib.parse import unquote, urlsplit
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

from lxml import etree


CONTAINER = "META-INF/container.xml"
MEDIA_TYPE = b"application/epub+zip"
OPF = "http://www.idpf.org/2007/opf"
DC = "http://purl.org/dc/elements/1.1/"
XHTML = "http://www.w3.org/1999/xhtml"
PROTECTION = {"META-INF/encryption.xml", "META-INF/rights.xml", "META-INF/signatures.xml"}
LIMIT_MEMBER = 256 * 1024**2
LIMIT_TOTAL = 2 * 1024**3
LIMIT_XML = 16 * 1024**2
CHUNK_SIZE = 1024**2


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha_file(path):
    with path.open("rb") as source:
        return file_digest(source, "sha256").hexdigest()


def parse_xml(data):
    parser = etree.XMLParser(
        no_network=True, load_dtd=False, resolve_entities=False,
        strip_cdata=False, recover=False, huge_tree=False,
    )
    return etree.parse(BytesIO(data), parser)


def safe_member(name):
    parts = name.removesuffix("/").split("/")
    return (
        all(part and part not in {".", ".."} for part in parts)
        and not any(char in name for char in ("\\", "\0", ":"))
    )


def xml_member(archive, name):
    require(archive.getinfo(name).file_size <= LIMIT_XML, f"XML exceeds size limit: {name}")
    return archive.read(name)


def check_zip(archive, stream):
    infos = archive.infolist()
    require(0 < len(infos) <= 50_000, "ZIP entry count outside supported limits")
    require(infos[0].filename == "mimetype", "mimetype must be the first ZIP entry")
    mime = infos[0]
    require(mime.header_offset == 0 and mime.compress_type == ZIP_STORED
            and not mime.extra and mime.file_size == len(MEDIA_TYPE), "Invalid mimetype ZIP entry")
    stream.seek(0)
    header = stream.read(30)
    require(len(header) == 30 and header[:4] == b"PK\x03\x04", "Invalid mimetype local ZIP header")
    flags, method = struct.unpack_from("<HH", header, 6)
    extra_size = struct.unpack_from("<H", header, 28)[0]
    require(not (flags & 1) and method == ZIP_STORED and extra_size == 0,
            "Invalid mimetype local ZIP flags, compression or extra field")
    names = set()
    total_size = 0
    for info in infos:
        name = info.filename
        require(info.orig_filename == name and safe_member(name), f"Unsafe ZIP path: {name!r}")
        require(name not in names, f"Duplicate ZIP entry: {name}")
        require(not (info.flag_bits & 1), f"Encrypted ZIP entry: {name}")
        require(not stat.S_ISLNK(info.external_attr >> 16), f"ZIP symlink: {name}")
        require(info.compress_type in {ZIP_STORED, ZIP_DEFLATED}, f"Unsupported ZIP compression: {name}")
        require(info.file_size <= LIMIT_MEMBER, f"ZIP entry exceeds size limit: {name}")
        total_size += info.file_size
        require(total_size <= LIMIT_TOTAL, "ZIP expanded size exceeds limit")
        names.add(name)
    require(archive.read(mime) == MEDIA_TYPE, "Unexpected mimetype content")
    return names


def local_href(package, href):
    url = urlsplit(href)
    if url.scheme or url.netloc:
        return None
    path = unquote(url.path, errors="strict")
    require(path and not path.startswith("/"), f"Invalid manifest href: {href!r}")
    member = posixpath.normpath(posixpath.join(posixpath.dirname(package), path))
    require(safe_member(member), f"Manifest href escapes package: {href!r}")
    return member


def inventory(archive, stream):
    names = check_zip(archive, stream)
    container = parse_xml(xml_member(archive, CONTAINER))
    namespace = "urn:oasis:names:tc:opendocument:xmlns:container"
    rootfiles = container.xpath(
        "/c:container/c:rootfiles/c:rootfile[@media-type='application/oebps-package+xml']/@full-path",
        namespaces={"c": namespace},
    )
    require(rootfiles, "No OPF package listed in container.xml")
    packages = []
    for package in rootfiles:
        require(package in names and not package.endswith("/"), f"Missing OPF package: {package}")
        root = parse_xml(xml_member(archive, package)).getroot()
        require(root.tag == f"{{{OPF}}}package", f"Invalid OPF root: {package}")
        manifest = root.findall(f"{{{OPF}}}manifest/{{{OPF}}}item")
        items = [
            {
                "id": item.get("id"), "href": item.get("href"),
                "member": local_href(package, item.get("href", "")),
                "media_type": item.get("media-type"),
                "properties": item.get("properties", "").split(),
            }
            for item in manifest
        ]
        members = {item["id"]: item["member"] for item in items if item["id"] is not None}
        namespaces = {"opf": OPF, "dc": DC}
        metadata = {
            field: root.xpath(f"opf:metadata/dc:{field}/text()", namespaces=namespaces)
            for field in ("title", "creator", "contributor", "language", "publisher", "date", "identifier", "source")
        }
        primary_id = root.get("unique-identifier")
        primary_identifier = root.xpath(
            "opf:metadata/dc:identifier[@id=$primary_id]/text()",
            namespaces=namespaces, primary_id=primary_id or "",
        )
        legacy_covers = set(root.xpath("opf:metadata/opf:meta[@name='cover']/@content", namespaces=namespaces))
        spine = root.find(f"{{{OPF}}}spine")
        itemrefs = [] if spine is None else spine.findall(f"{{{OPF}}}itemref")
        spine_items = [
            {
                "idref": ref.get("idref"), "member": members.get(ref.get("idref")),
                "linear": ref.get("linear", "yes"),
            }
            for ref in itemrefs
        ]
        ncx_ids = root.xpath("opf:spine/@toc", namespaces=namespaces)
        packages.append({
            "member": package, "version": root.get("version"),
            "titles": metadata["title"], "metadata": metadata,
            "primary_identifier": primary_identifier[0] if len(primary_identifier) == 1 else None,
            "manifest": items,
            "spine": [item["idref"] for item in spine_items if item["idref"] is not None],
            "spine_items": spine_items,
            "page_progression_direction": spine.get("page-progression-direction", "default") if spine is not None else None,
            "ncx_id": ncx_ids, "ncx_member": members.get(ncx_ids[0]) if ncx_ids else None,
            "nav_members": [item["member"] for item in items if item["member"] and "nav" in item["properties"]],
            "cover_members": [
                item["member"] for item in items
                if item["member"] and ("cover-image" in item["properties"] or item["id"] in legacy_covers)
            ],
        })
    return {"entry_count": len(names), "protection": sorted(PROTECTION & names), "packages": packages}


def archive_hashes(archive):
    result = {}
    for info in archive.infolist():
        with archive.open(info) as stream:
            result[info.filename] = file_digest(stream, "sha256").hexdigest()
    return result


def repack(archive, candidate, replacements):
    before = {}
    with ZipFile(candidate, "x") as output:
        output.comment = archive.comment
        for info in archive.infolist():
            name = info.filename
            with archive.open(info) as source, output.open(copy(info), "w") as target:
                if name in replacements:
                    before[name] = file_digest(source, "sha256").hexdigest()
                    target.write(replacements[name])
                else:
                    digest = sha256()
                    while chunk := source.read(CHUNK_SIZE):
                        digest.update(chunk)
                        target.write(chunk)
                    before[name] = digest.hexdigest()
    with candidate.open("rb") as stream, ZipFile(stream) as output:
        check_zip(output, stream)
        require(
            [(i.filename, i.compress_type) for i in output.infolist()]
            == [(i.filename, i.compress_type) for i in archive.infolist()],
            "ZIP entry order, names or compression methods changed",
        )
        after = archive_hashes(output)
    require({name for name in before if before[name] != after[name]} == replacements.keys(),
            "Archive changes differ from approved plan")
    require(all(after[name] == sha256(data).hexdigest() for name, data in replacements.items()),
            "Output differs from approved replacement")
    return before, after


def spine_signature(book, archive):
    result = []
    archive_members = set(archive.namelist())
    for package in book["packages"]:
        sequence = [(item["member"], item["linear"]) for item in package["spine_items"]]
        require(
            sequence and all(member in archive_members and linear in {"yes", "no"} for member, linear in sequence),
            f"Cannot resolve reading order for {package['member']}",
        )
        result.append((package["member"], package["page_progression_direction"], sequence))
    return result


def reading_text_hashes(book, archive):
    """Hash body text of spine XHTML documents, excluding EPUB 3 navigation."""
    hashes = {}
    for package in book["packages"]:
        documents = {item["member"] for item in package["manifest"]
                     if item["media_type"] == "application/xhtml+xml"}
        for entry in package["spine_items"]:
            member = entry["member"]
            if member not in documents or member in package["nav_members"] or member in hashes:
                continue
            body = parse_xml(xml_member(archive, member)).getroot().find(f"{{{XHTML}}}body")
            require(body is not None, f"Missing XHTML body: {member}")
            text = re.sub(r"[ \t\r\n]+", " ", "".join(body.itertext())).strip(" ")
            hashes[member] = sha256(text.encode("utf-8")).hexdigest()
    return hashes
