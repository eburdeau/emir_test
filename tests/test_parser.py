"""Tests de flatten_datrec."""

import tracemalloc
from pathlib import Path
from textwrap import dedent

import pandas as pd
import pytest

from datrec_parser import flatten_datrec

FIXTURES = Path(__file__).parent / "fixtures"
OUTPUTS = Path(__file__).parent / "outputs"

NS = 'xmlns="urn:iso:std:iso:20022:tech:xsd:auth.091.001.02"'


def _make_rcncltn_rpt(tx_id: str) -> str:
    return dedent(f"""\
        <RcncltnRpt>
          <TxId><UnqIdr><UnqTxIdr><Id>{tx_id}</Id></UnqTxIdr></UnqIdr></TxId>
          <MtchgCrit>
            <CtrPtyMtchgCrit>
              <DrctnOrSd><Val><Tp>RECO</Tp></Val></DrctnOrSd>
            </CtrPtyMtchgCrit>
          </MtchgCrit>
        </RcncltnRpt>""")


def _make_tx_dtls(tx_dtls_idx: int, n_rpts: int) -> str:
    lei = f"LEI{tx_dtls_idx:018d}"
    rpts = "\n".join(_make_rcncltn_rpt(f"TX{tx_dtls_idx:06d}_{i:04d}") for i in range(n_rpts))
    return dedent(f"""\
        <TxDtls>
          <CtrPtyId><RptgCtrPty><LEI>{lei}</LEI></RptgCtrPty></CtrPtyId>
          <TtlNbOfTxs>{n_rpts}</TtlNbOfTxs>
          {rpts}
        </TxDtls>""")


def _generate_large_xml(path: Path, n_tx_dtls: int, rpts_per_tx: int) -> int:
    """Écrit un fichier XML DATREC avec n_tx_dtls × rpts_per_tx lignes. Retourne le nb de lignes."""
    tx_dtls_blocks = "\n".join(_make_tx_dtls(i, rpts_per_tx) for i in range(n_tx_dtls))
    total = n_tx_dtls * rpts_per_tx
    xml = dedent(f"""\
        <?xml version="1.0" encoding="UTF-8"?>
        <Document {NS}>
          <DerivsTradRcncltnSttstclRpt>
            <RcncltnSttstcs>
              <Rpt>
                <RefDt>2024-06-01</RefDt>
                <RcncltnCtgrs>
                  <Rvvd>
                    <RptgCtrPty><LEI>529900T8BM49AURSDO55</LEI></RptgCtrPty>
                    <OthrCtrPty><Lgl><Id><LEI>AAAAAAAAAAAAAAAAAA01</LEI></Id></Lgl></OthrCtrPty>
                  </Rvvd>
                </RcncltnCtgrs>
                <TtlNbOfTxs>{total}</TtlNbOfTxs>
                {tx_dtls_blocks}
              </Rpt>
            </RcncltnSttstcs>
          </DerivsTradRcncltnSttstclRpt>
        </Document>""")
    path.write_text(xml, encoding="utf-8")
    return total


class TestDataSetAction:
    """Cas 1 : RcncltnSttstcs contient DataSetActn (aucune donnée de transaction)."""

    def test_returns_dataframe(self):
        df = flatten_datrec(FIXTURES / "datrec_dataset_action.xml")
        assert isinstance(df, pd.DataFrame)

    def test_single_row(self):
        df = flatten_datrec(FIXTURES / "datrec_dataset_action.xml")
        assert len(df) == 1

    def test_dataset_action_value(self):
        df = flatten_datrec(FIXTURES / "datrec_dataset_action.xml")
        assert df["RcncltnSttstcs__DataSetActn"].iloc[0] == "NACT"

    def test_csv_output(self):
        out = OUTPUTS / "datrec_dataset_action.csv"
        flatten_datrec(FIXTURES / "datrec_dataset_action.xml", output_csv=out)
        assert out.exists()


class TestMinimalFile:
    """Cas 2 : un seul Rpt avec un TxDtls et deux RcncltnRpt."""

    def test_returns_dataframe(self):
        df = flatten_datrec(FIXTURES / "datrec_minimal.xml")
        assert isinstance(df, pd.DataFrame)

    def test_row_count(self):
        df = flatten_datrec(FIXTURES / "datrec_minimal.xml")
        assert len(df) == 2

    def test_ref_dt_propagated(self):
        df = flatten_datrec(FIXTURES / "datrec_minimal.xml")
        assert (df["Rpt__RefDt"] == "2024-01-15").all()

    def test_rpt_total_txs(self):
        df = flatten_datrec(FIXTURES / "datrec_minimal.xml")
        assert (df["Rpt__TtlNbOfTxs"] == "2").all()

    def test_ctr_pty_lei_present(self):
        df = flatten_datrec(FIXTURES / "datrec_minimal.xml")
        col = "TxDtls__CtrPtyId__RptgCtrPty__LEI"
        assert col in df.columns, f"colonnes disponibles : {list(df.columns)}"
        assert (df[col] == "529900T8BM49AURSDO55").all()

    def test_utis_distinct(self):
        df = flatten_datrec(FIXTURES / "datrec_minimal.xml")
        col = "RcncltnRpt__TxId__UnqIdr__UnqTxIdr__Id"
        assert col in df.columns, f"colonnes disponibles : {list(df.columns)}"
        utis = df[col].tolist()
        assert "529900T8BM49AURSDO550000000001" in utis
        assert "529900T8BM49AURSDO550000000002" in utis

    def test_matching_criteria_present(self):
        df = flatten_datrec(FIXTURES / "datrec_minimal.xml")
        col = "RcncltnRpt__MtchgCrit__CtrPtySd__DrctnOrSd__Val__Tp"
        assert col in df.columns, f"colonnes disponibles : {list(df.columns)}"

    def test_missing_optional_fields_are_nan(self):
        df = flatten_datrec(FIXTURES / "datrec_minimal.xml")
        col = "RcncltnRpt__MtchgCrit__TxDtls__CtrctTp__Val__Tp"
        assert col in df.columns, f"colonnes disponibles : {list(df.columns)}"
        # La 2e ligne n'a pas ce champ (MtchgCrit sans TxDtls)
        assert pd.isna(df[col].iloc[1])

    def test_csv_output(self):
        out = OUTPUTS / "datrec_minimal.csv"
        flatten_datrec(FIXTURES / "datrec_minimal.xml", output_csv=out)
        assert out.exists()


class TestMultiRpt:
    """Cas 3 : plusieurs Rpt avec dates différentes."""

    def test_row_count(self):
        df = flatten_datrec(FIXTURES / "datrec_multi_rpt.xml")
        assert len(df) == 3  # 1 + 2 RcncltnRpt

    def test_ref_dt_values(self):
        df = flatten_datrec(FIXTURES / "datrec_multi_rpt.xml")
        dates = df["Rpt__RefDt"].tolist()
        assert "2024-01-14" in dates
        assert "2024-01-15" in dates

    def test_first_rpt_date_on_single_row(self):
        df = flatten_datrec(FIXTURES / "datrec_multi_rpt.xml")
        assert df[df["Rpt__RefDt"] == "2024-01-14"].shape[0] == 1

    def test_second_rpt_date_on_two_rows(self):
        df = flatten_datrec(FIXTURES / "datrec_multi_rpt.xml")
        assert df[df["Rpt__RefDt"] == "2024-01-15"].shape[0] == 2

    def test_uti_values(self):
        df = flatten_datrec(FIXTURES / "datrec_multi_rpt.xml")
        col = "RcncltnRpt__TxId__UnqIdr__UnqTxIdr__Id"
        assert col in df.columns, f"colonnes disponibles : {list(df.columns)}"
        utis = set(df[col].tolist())
        assert utis == {"RPT1TX001", "RPT2TX001", "RPT2TX002"}

    def test_csv_output(self):
        out = OUTPUTS / "datrec_multi_rpt.csv"
        flatten_datrec(FIXTURES / "datrec_multi_rpt.xml", output_csv=out)
        assert out.exists()


class TestCsvExport:
    """Cas 4 : export CSV — vérifie le mécanisme d'écriture (fichier, contenu, valeurs)."""

    _out = OUTPUTS / "datrec_csv_export.csv"

    def test_csv_created(self):
        flatten_datrec(FIXTURES / "datrec_minimal.xml", output_csv=self._out)
        assert self._out.exists()

    def test_csv_readable(self):
        df = flatten_datrec(FIXTURES / "datrec_minimal.xml", output_csv=self._out)
        df_read = pd.read_csv(self._out)
        assert len(df_read) == len(df)
        assert list(df_read.columns) == list(df.columns)

    def test_csv_values_preserved(self):
        df = flatten_datrec(FIXTURES / "datrec_minimal.xml", output_csv=self._out)
        df_read = pd.read_csv(self._out)
        assert df_read["Rpt__RefDt"].iloc[0] == df["Rpt__RefDt"].iloc[0]


class TestMultivalFields:
    """Cas 5 : enfants répétés dans MtchgCrit > TxMtchgCrit.

    TxMtchgCrit contient 3 × OthrPmt et 2 × NtnlAmtFrstLegSchdlAmt.
    La fonction doit générer des colonnes suffixées __0, __1, __2 au lieu
    d'écraser les valeurs précédentes.
    """

    @pytest.fixture(scope="class")
    def df(self):
        return flatten_datrec(FIXTURES / "datrec_multival.xml")

    def test_single_row(self, df):
        assert len(df) == 1

    # --- OthrPmt (3 occurrences) ---

    def test_otherpmt_columns_exist(self, df):
        for i in range(3):
            col = f"RcncltnRpt__MtchgCrit__TxMtchgCrit__OthrPmt__{i}__OthrPmtTp__Val1__Tp"
            assert col in df.columns, (
                f"colonne manquante pour OthrPmt__{i} ; colonnes : {[c for c in df.columns if 'OthrPmt' in c]}"
            )

    def test_otherpmt_0_type(self, df):
        col = "RcncltnRpt__MtchgCrit__TxMtchgCrit__OthrPmt__0__OthrPmtTp__Val1__Tp"
        assert df[col].iloc[0] == "INTR"

    def test_otherpmt_1_type(self, df):
        col = "RcncltnRpt__MtchgCrit__TxMtchgCrit__OthrPmt__1__OthrPmtTp__Val1__Tp"
        assert df[col].iloc[0] == "CEAR"

    def test_otherpmt_2_type(self, df):
        col = "RcncltnRpt__MtchgCrit__TxMtchgCrit__OthrPmt__2__OthrPmtTp__Val1__Tp"
        assert df[col].iloc[0] == "PREMIUM"

    def test_otherpmt_dates_distinct(self, df):
        dates = [
            df[f"RcncltnRpt__MtchgCrit__TxMtchgCrit__OthrPmt__{i}__OthrPmtDt__Val1"].iloc[0]
            for i in range(3)
        ]
        assert dates == ["2024-01-15", "2024-02-15", "2024-03-15"]

    def test_otherpmt_val2_present_for_0_and_absent_for_2(self, df):
        col_0 = "RcncltnRpt__MtchgCrit__TxMtchgCrit__OthrPmt__0__OthrPmtTp__Val2__Tp"
        col_2 = "RcncltnRpt__MtchgCrit__TxMtchgCrit__OthrPmt__2__OthrPmtTp__Val2__Tp"
        # OthrPmt 0 a un Val2 → colonne présente avec valeur
        assert df[col_0].iloc[0] == "INTR"
        # OthrPmt 2 n'a pas de Val2 → la colonne n'est pas créée du tout
        # (pd.DataFrame ne crée pas de colonne entièrement absente dans tous les dicts)
        assert col_2 not in df.columns

    # --- NtnlAmtFrstLegSchdlAmt (2 occurrences) ---

    def test_notional_columns_exist(self, df):
        for i in range(2):
            col = f"RcncltnRpt__MtchgCrit__TxMtchgCrit__NtnlAmtFrstLegSchdlAmt__{i}__Val1__Amt__@Ccy"
            assert col in df.columns, (
                f"colonne manquante pour NtnlAmtFrstLegSchdlAmt__{i} ; "
                f"colonnes : {[c for c in df.columns if 'NtnlAmt' in c]}"
            )

    def test_notional_0_currency(self, df):
        col = "RcncltnRpt__MtchgCrit__TxMtchgCrit__NtnlAmtFrstLegSchdlAmt__0__Val1__Amt__@Ccy"
        assert df[col].iloc[0] == "EUR"

    def test_notional_1_currency(self, df):
        col = "RcncltnRpt__MtchgCrit__TxMtchgCrit__NtnlAmtFrstLegSchdlAmt__1__Val1__Amt__@Ccy"
        assert df[col].iloc[0] == "USD"

    def test_no_column_overwrite(self, df):
        """Vérifie qu'OthrPmt__0 et OthrPmt__1 ont des valeurs distinctes (pas d'écrasement)."""
        tp0 = df["RcncltnRpt__MtchgCrit__TxMtchgCrit__OthrPmt__0__OthrPmtTp__Val1__Tp"].iloc[0]
        tp1 = df["RcncltnRpt__MtchgCrit__TxMtchgCrit__OthrPmt__1__OthrPmtTp__Val1__Tp"].iloc[0]
        assert tp0 != tp1

    def test_csv_output(self, df):
        out = OUTPUTS / "datrec_multival.csv"
        flatten_datrec(FIXTURES / "datrec_multival.xml", output_csv=out)
        assert out.exists()


class TestCmmdtyGrnOilSeed:
    """Cas 6 : Cmmdty > Agrcltrl > GrnOilSeed dans TxMtchgCrit.

    Val1 = SOYB, Val2 = RPSD → non-réconciliation sur AddtlSubPdct.
    Vérifie que BasePdct, SubPdct et AddtlSubPdct sont correctement aplatis
    pour les deux côtés de la comparaison.
    """

    _COL_BASE = "RcncltnRpt__MtchgCrit__TxMtchgCrit__Cmmdty__{side}__Agrcltrl__GrnOilSeed__{field}"

    @pytest.fixture(scope="class")
    def df(self):
        return flatten_datrec(FIXTURES / "datrec_cmmdty_grnoilseed.xml")

    def _col(self, side: str, field: str) -> str:
        return self._COL_BASE.format(side=side, field=field)

    def test_single_row(self, df):
        assert len(df) == 1

    def test_ref_dt(self, df):
        assert df["Rpt__RefDt"].iloc[0] == "2024-06-01"

    def test_uti(self, df):
        col = "RcncltnRpt__TxId__UnqIdr__UnqTxIdr"
        assert col in df.columns, f"colonnes disponibles : {list(df.columns)}"
        assert df[col].iloc[0] == "GRNOILSEED_TX_001"

    # --- colonnes présentes ---

    def test_grnoilseed_columns_exist(self, df):
        for side in ("Val1", "Val2"):
            for field in ("BasePdct", "SubPdct", "AddtlSubPdct"):
                col = self._col(side, field)
                assert col in df.columns, (
                    f"colonne manquante : {col}\n"
                    f"colonnes Cmmdty disponibles : {[c for c in df.columns if 'Cmmdty' in c]}"
                )

    # --- valeurs Val1 ---

    def test_val1_base_pdct(self, df):
        assert df[self._col("Val1", "BasePdct")].iloc[0] == "AGRI"

    def test_val1_sub_pdct(self, df):
        assert df[self._col("Val1", "SubPdct")].iloc[0] == "GROS"

    def test_val1_addtl_sub_pdct(self, df):
        assert df[self._col("Val1", "AddtlSubPdct")].iloc[0] == "SOYB"

    # --- valeurs Val2 ---

    def test_val2_base_pdct(self, df):
        assert df[self._col("Val2", "BasePdct")].iloc[0] == "AGRI"

    def test_val2_sub_pdct(self, df):
        assert df[self._col("Val2", "SubPdct")].iloc[0] == "GROS"

    def test_val2_addtl_sub_pdct(self, df):
        assert df[self._col("Val2", "AddtlSubPdct")].iloc[0] == "RPSD"

    # --- non-réconciliation ---

    def test_addtl_sub_pdct_mismatch(self, df):
        """Val1 et Val2 ont des AddtlSubPdct différents → non-réconciliation."""
        val1 = df[self._col("Val1", "AddtlSubPdct")].iloc[0]
        val2 = df[self._col("Val2", "AddtlSubPdct")].iloc[0]
        assert val1 != val2

    def test_csv_output(self, df):
        out = OUTPUTS / "datrec_cmmdty_grnoilseed.csv"
        flatten_datrec(FIXTURES / "datrec_cmmdty_grnoilseed.xml", output_csv=out)
        assert out.exists()


class TestLargeFile:
    """Cas 6 : fichier volumineux généré — vérification du nombre de lignes et de la mémoire."""

    N_TX_DTLS = 100
    RPTS_PER_TX = 100  # 10 000 lignes au total

    @pytest.fixture(scope="class")
    def large_xml(self, tmp_path_factory):
        path = tmp_path_factory.mktemp("large") / "datrec_large.xml"
        _generate_large_xml(path, self.N_TX_DTLS, self.RPTS_PER_TX)
        return path

    def test_row_count(self, large_xml):
        df = flatten_datrec(large_xml)
        assert len(df) == self.N_TX_DTLS * self.RPTS_PER_TX

    def test_ref_dt_consistent(self, large_xml):
        df = flatten_datrec(large_xml)
        assert (df["Rpt__RefDt"] == "2024-06-01").all()

    def test_uti_unique(self, large_xml):
        df = flatten_datrec(large_xml)
        col = "RcncltnRpt__TxId__UnqIdr__UnqTxIdr__Id"
        assert df[col].nunique() == self.N_TX_DTLS * self.RPTS_PER_TX

    def test_csv_output(self, large_xml):
        out = OUTPUTS / "datrec_large.csv"
        flatten_datrec(large_xml, output_csv=out)
        assert out.exists()

    def test_streaming_peak_memory(self, large_xml):
        """Le pic mémoire Python doit rester < 3× la taille du fichier XML.

        Avec iterparse, un seul Rpt est en mémoire à la fois. Le fichier fait
        plusieurs Mo ; le DOM complet serait bien plus lourd.
        """
        file_size = large_xml.stat().st_size

        tracemalloc.start()
        flatten_datrec(large_xml)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        assert peak < file_size * 3, (
            f"pic mémoire Python ({peak/1024:.0f} KB) trop élevé "
            f"par rapport à la taille du fichier ({file_size/1024:.0f} KB)"
        )
