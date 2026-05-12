"""
Namespace constants and XPath helpers for auth.091.001.02 (DATREC).
All XPath expressions must use the 'a' prefix mapped to NS["a"].
"""

NS = {
    "a": "urn:iso:std:iso:20022:tech:xsd:auth.091.001.02",
    "head": "urn:iso:std:iso:20022:tech:xsd:head.001.001.01",
}

XSD_PATH = (
    "EMIR Refit - Outgoing Messages - FINAL - V1.1.0/"
    "auth.091.001.02_ESMAUG_DATREC_1.0.0.xsd"
)

# Root path to the report body
_RPT_ROOT = "a:Document/a:DerivsTradRcncltnSttstclRpt/a:RcncltnSttstcs"

# XPath to the DataSetAction element (choice 1 — no trade data)
XPATH_DATASET_ACTION = f"{_RPT_ROOT}/a:DataSetActn"

# XPath to iterate over Rpt elements (choice 2)
XPATH_RPT = f"{_RPT_ROOT}/a:Rpt"

# Relative paths inside each Rpt
XPATH_REF_DT = "a:RefDt"
XPATH_RCNCLTN_CTGRS = "a:RcncltnCtgrs"
XPATH_RPT_TTL_TXS = "a:TtlNbOfTxs"
XPATH_TX_DTLS = "a:TxDtls"

# Relative paths inside TxDtls
XPATH_CTR_PTY_ID = "a:CtrPtyId"
XPATH_TX_DTLS_TTL_TXS = "a:TtlNbOfTxs"
XPATH_RCNCLTN_RPT = "a:RcncltnRpt"

# Relative paths inside CtrPtyId
XPATH_RPTG_CTR_PTY = "a:CtrPtyId/a:RptgCtrPty"
XPATH_OTHR_CTR_PTY = "a:CtrPtyId/a:OthrCtrPty"
XPATH_RPT_SUBMITG_NTTY = "a:CtrPtyId/a:RptSubmitgNtty"
XPATH_NTTY_RSPNSBL = "a:CtrPtyId/a:NttyRspnsblForRpt"

# Relative paths inside RcncltnRpt
XPATH_TX_ID = "a:TxId"
XPATH_MTCHG_CRIT = "a:MtchgCrit"
