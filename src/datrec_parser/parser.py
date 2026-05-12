"""
flatten_datrec — mise à plat de fichiers XML DATREC (auth.091.001.02).

Hiérarchie du message :
  Document
  └── DerivsTradRcncltnSttstclRpt
      └── RcncltnSttstcs  (choice)
          ├── DataSetActn  → DataFrame vide (1 ligne avec la valeur)
          └── Rpt[]
              ├── RefDt, RcncltnCtgrs, TtlNbOfTxs
              └── TxDtls[]
                  ├── CtrPtyId (RptgCtrPty, OthrCtrPty, RptSubmitgNtty, NttyRspnsblForRpt)
                  ├── TtlNbOfTxs
                  └── RcncltnRpt[]  ← grain de la ligne de sortie
                      ├── TxId / UnqIdr
                      └── MtchgCrit (champs aplatis récursivement)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
from lxml import etree

from .schema import NS, XPATH_DATASET_ACTION, XPATH_RPT

_NS_URI = NS["a"]
_NS_MAP = NS


def _tag_local(element: etree._Element) -> str:
    """Retourne le nom local de la balise sans namespace."""
    tag = element.tag
    if tag.startswith("{"):
        return tag.split("}", 1)[1]
    return tag


def _flatten_element(
    element: etree._Element,
    prefix: str = "",
    _key: str | None = None,
) -> dict[str, Any]:
    """
    Aplatit récursivement un élément XML en dict plat.

    Conventions :
    - Séparateur de niveau : "__"
    - Les attributs XML sont inclus sous la forme  clé__@attr
    - Les éléments à contenu textuel simple : clé = texte
    - Les enfants répétés (même tag) sont suffixés __0, __1, __2 …

    _key permet de passer une clé complète calculée par le parent (cas des enfants
    indexés) en court-circuitant le calcul automatique prefix__local.
    """
    result: dict[str, Any] = {}
    local = _tag_local(element)
    key = _key if _key is not None else (f"{prefix}__{local}" if prefix else local)

    # Attributs XML (ex. Ccy="EUR")
    for attr_name, attr_val in element.attrib.items():
        result[f"{key}__@{attr_name}"] = attr_val

    # callable(tag) filtre les commentaires et PI lxml (etree._Comment, etc.)
    children = [c for c in element if not callable(c.tag)]

    if not children:
        text = (element.text or "").strip()
        result[key] = text if text else None
        return result

    # Comptage des enfants homonymes pour détecter les listes
    child_tag_counts: dict[str, int] = {}
    for child in children:
        clocal = _tag_local(child)
        child_tag_counts[clocal] = child_tag_counts.get(clocal, 0) + 1

    child_indices: dict[str, int] = {}
    for child in children:
        clocal = _tag_local(child)
        if child_tag_counts[clocal] > 1:
            idx = child_indices.get(clocal, 0)
            child_indices[clocal] = idx + 1
            # Passe la clé indexée complète pour que la récursion ne la modifie pas
            sub = _flatten_element(child, _key=f"{key}__{clocal}__{idx}")
        else:
            sub = _flatten_element(child, prefix=key)
        result.update(sub)

    return result


def _extract_org_id(element: etree._Element | None, prefix: str) -> dict[str, Any]:
    """Extrait l'identifiant d'une organisation (LEI ou autre) d'un élément Choice."""
    if element is None:
        return {}
    return _flatten_element(element, prefix=prefix)


def _build_rpt_context(rpt: etree._Element) -> dict[str, Any]:
    """Construit le contexte de niveau Rpt (RefDt, RcncltnCtgrs, TtlNbOfTxs)."""
    ctx: dict[str, Any] = {}

    ref_dt = rpt.find("a:RefDt", _NS_MAP)
    ctx["Rpt__RefDt"] = ref_dt.text.strip() if ref_dt is not None and ref_dt.text else None

    rcncltn_ctgrs = rpt.find("a:RcncltnCtgrs", _NS_MAP)
    if rcncltn_ctgrs is not None:
        ctx.update(_flatten_element(rcncltn_ctgrs, prefix="Rpt"))

    ttl = rpt.find("a:TtlNbOfTxs", _NS_MAP)
    ctx["Rpt__TtlNbOfTxs"] = ttl.text.strip() if ttl is not None and ttl.text else None

    return ctx


def _build_tx_dtls_context(tx_dtls: etree._Element) -> dict[str, Any]:
    """Construit le contexte de niveau TxDtls (identifiants contreparties + total)."""
    ctx: dict[str, Any] = {}

    ctr_pty = tx_dtls.find("a:CtrPtyId", _NS_MAP)
    if ctr_pty is not None:
        for child_tag in [
            "a:RptgCtrPty",
            "a:OthrCtrPty",
            "a:RptSubmitgNtty",
            "a:NttyRspnsblForRpt",
        ]:
            child = ctr_pty.find(child_tag, _NS_MAP)
            if child is not None:
                # prefix = parent path; _flatten_element appends the child's local name
                ctx.update(_flatten_element(child, prefix="TxDtls__CtrPtyId"))

    ttl = tx_dtls.find("a:TtlNbOfTxs", _NS_MAP)
    ctx["TxDtls__TtlNbOfTxs"] = ttl.text.strip() if ttl is not None and ttl.text else None

    return ctx


def _build_rcncltn_rpt_row(
    rcncltn_rpt: etree._Element,
    rpt_ctx: dict[str, Any],
    tx_dtls_ctx: dict[str, Any],
) -> dict[str, Any]:
    """Construit une ligne à partir d'un élément RcncltnRpt et de ses contextes parents."""
    row: dict[str, Any] = {}
    row.update(rpt_ctx)
    row.update(tx_dtls_ctx)

    tx_id = rcncltn_rpt.find("a:TxId", _NS_MAP)
    if tx_id is not None:
        row.update(_flatten_element(tx_id, prefix="RcncltnRpt"))

    mtchg_crit = rcncltn_rpt.find("a:MtchgCrit", _NS_MAP)
    if mtchg_crit is not None:
        row.update(_flatten_element(mtchg_crit, prefix="RcncltnRpt"))

    return row


def flatten_datrec(
    xml_path: str | Path,
    output_csv: str | Path | None = None,
    validate: bool = False,
) -> pd.DataFrame:
    """
    Met à plat un fichier XML DATREC (auth.091.001.02) en DataFrame pandas.

    Chaque ligne correspond à un enregistrement RcncltnRpt. Les champs parents
    (Rpt, TxDtls, CtrPtyId) sont répétés sur chaque ligne (dénormalisation).

    Paramètres
    ----------
    xml_path : chemin vers le fichier XML DATREC (ou enveloppe avec BAH).
    output_csv : si fourni, écrit le résultat en CSV à ce chemin.
    validate : si True, valide le XML contre le XSD avant parsing (coûteux).

    Retourne
    --------
    pd.DataFrame — une ligne par RcncltnRpt, NaN pour les champs absents.
    """
    xml_path = Path(xml_path)

    if validate:
        _validate_xml(xml_path)

    rows: list[dict[str, Any]] = []

    # Streaming via iterparse — libère la mémoire au fur et à mesure.
    # On cible l'élément Rpt pour traiter un rapport à la fois.
    rpt_tag = f"{{{_NS_URI}}}Rpt"
    dataset_action_tag = f"{{{_NS_URI}}}DataSetActn"

    context = etree.iterparse(
        str(xml_path),
        events=("end",),
        tag=[rpt_tag, dataset_action_tag],
        recover=True,
    )

    for event, element in context:
        local = _tag_local(element)

        if local == "DataSetActn":
            # Cas 1 : pas de données, on retourne une seule ligne avec la valeur
            rows.append({"RcncltnSttstcs__DataSetActn": (element.text or "").strip()})
            _free(element)
            continue

        if local == "Rpt":
            rpt_ctx = _build_rpt_context(element)

            tx_dtls_list = element.findall("a:TxDtls", _NS_MAP)
            if not tx_dtls_list:
                # Rpt sans TxDtls : une ligne de contexte seul
                rows.append(rpt_ctx)
            else:
                for tx_dtls in tx_dtls_list:
                    tx_ctx = _build_tx_dtls_context(tx_dtls)

                    rcncltn_rpts = tx_dtls.findall("a:RcncltnRpt", _NS_MAP)
                    for rcncltn_rpt in rcncltn_rpts:
                        rows.append(_build_rcncltn_rpt_row(rcncltn_rpt, rpt_ctx, tx_ctx))

            _free(element)

    df = pd.DataFrame(rows)

    if output_csv is not None:
        df.to_csv(output_csv, index=False, encoding="utf-8")

    return df


def _free(element: etree._Element) -> None:
    """Libère l'élément et ses ancêtres du DOM pour économiser la mémoire."""
    element.clear()
    parent = element.getparent()
    if parent is not None:
        # Supprime les frères déjà traités (avant cet élément)
        while parent[0] is not element:
            del parent[0]


def _validate_xml(xml_path: Path) -> None:
    """Valide xml_path contre le XSD DATREC. Lève etree.DocumentInvalid si invalide."""
    xsd_path = xml_path.parent.parent / (
        "EMIR Refit - Outgoing Messages - FINAL - V1.1.0/"
        "auth.091.001.02_ESMAUG_DATREC_1.0.0.xsd"
    )
    if not xsd_path.exists():
        raise FileNotFoundError(f"XSD introuvable : {xsd_path}")
    schema_doc = etree.parse(str(xsd_path))
    schema = etree.XMLSchema(schema_doc)
    doc = etree.parse(str(xml_path))
    schema.assertValid(doc)
