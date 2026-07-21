import re
from typing import Dict, List

import pdfplumber


class MoniepointPDFParser:
    """
    Production-ready Moniepoint PDF parser.

    Extraction strategy:

        1. Parse structured tables.
        2. Parse raw page text.
        3. Merge both results.
        4. Remove duplicates.
        5. Validate output.
    """

    # ==========================================================
    # Constructor
    # ==========================================================

    def __init__(self, file_path: str, debug: bool = False):

        self.file_path = file_path

        self.debug = debug

    # ==========================================================
    # Main Entry Point
    # ==========================================================

    def extract(self) -> Dict:

        if self.debug:
            print("\n" + "=" * 80)
            print("MONIEPOINT PDF PARSER v2.0")
            print("=" * 80)

        try:

            table_transactions = self._extract_from_tables()

            if self.debug:
                print(
                    f"\nTable Transactions : "
                    f"{len(table_transactions)}"
                )

            text_transactions = self._extract_from_text()

            if self.debug:
                print(
                    f"Text Transactions  : "
                    f"{len(text_transactions)}"
                )

            transactions = self._merge_transactions(
                table_transactions,
                text_transactions,
            )

            if self.debug:
                print(
                    f"Final Transactions : "
                    f"{len(transactions)}"
                )

            confidence = self._calculate_confidence(
                transactions
            )

            return {

                "success": len(transactions) > 0,

                "transaction_count": len(transactions),

                "transactions": transactions,

                "confidence_score": confidence,

                "errors": [],

                "provider": "Moniepoint",

                "source_format": "pdf",

            }

        except Exception as e:

            return self._failure(
                [f"{type(e).__name__}: {e}"]
            )

    # ==========================================================
    # TABLE EXTRACTION
    # ==========================================================

    def _extract_from_tables(self):

        tables = self._read_tables()

        if self.debug:
            print("\n" + "=" * 80)
            print("TABLE EXTRACTION")
            print("=" * 80)
            print(f"Tables Found: {len(tables)}")

        # Flatten all rows from every table, in document order. This
        # matters because pdfplumber's "lines" table-detection
        # sometimes splits ONE logical transaction row into two
        # separate one-row "tables": the real data row (with a
        # truncated date cell, e.g. "2026-\n05-\n01T09:") followed
        # immediately by a phantom continuation row carrying just
        # the missing date tail (verified against the real
        # statement: ['00:12', '-', '', '', ...] with every other
        # field blank). That phantom always immediately follows its
        # real row, but the two can land in different `table`
        # entries in the `tables` list, so the merge has to operate
        # across table boundaries, not within a single table's rows.

        flat_rows = []

        for table in tables:

            if not table:
                continue

            for row in table:

                flat_rows.append(row)

        merged_rows = []

        for row in flat_rows:

            if not row or not any(row):
                continue

            cells = [
                "" if c is None else str(c).strip()
                for c in row
            ]

            first_cell = cells[0].replace("\n", "") if cells else ""

            amount_cell = cells[8] if len(cells) > 8 else ""

            is_phantom = (
                merged_rows
                and bool(re.match(r"^\d{1,2}:\d{1,2}$", first_cell))
                and not amount_cell
            )

            if is_phantom:

                prev = merged_rows[-1]

                prev[0] = (prev[0] or "") + cells[0]

                if self.debug:
                    print(
                        f"Merged phantom date fragment "
                        f"{cells[0]!r} into previous row"
                    )

                continue

            merged_rows.append(list(row))

        transactions = []

        for row in merged_rows:

            txn = self._parse_table_row(row)

            if txn:
                transactions.append(txn)

        if self.debug:
            print(
                f"\nTable Transactions Parsed : "
                f"{len(transactions)}"
            )

        return transactions

    # ==========================================================
    # Read every table from the PDF
    # ==========================================================

    def _read_tables(self):

        all_tables = []

        with pdfplumber.open(self.file_path) as pdf:

            for page_no, page in enumerate(pdf.pages, start=1):

                page_tables = page.extract_tables()

                if self.debug:
                    print(
                        f"Page {page_no}: "
                        f"{len(page_tables)} table(s)"
                    )

                all_tables.extend(page_tables)

        return all_tables

    # ==========================================================
    # Parse one table row
    # ==========================================================

    def _parse_table_row(self, row):

        if not row:
            return None

        row = [
            "" if cell is None else str(cell).strip()
            for cell in row
        ]

        if not any(row):
            return None

        while len(row) < 19:
            row.append("")

        # ------------------------------------------------------
        # Core Fields
        # ------------------------------------------------------

        raw_date = self._normalize_date(row[0])

        narration = row[18].replace("\n", " ").strip()

        upper = narration.upper()

        transaction_type = row[2].upper()

        # ------------------------------------------------------
        # Transaction Classification & Provider Detection
        # ------------------------------------------------------

        service_type, is_levy_line = self._classify_service(
            upper, transaction_type
        )

        provider = self._detect_provider(upper)

        # ------------------------------------------------------
        # Monetary Values
        # ------------------------------------------------------

        amount = self._to_float(row[8])

        debit = self._to_float(row[9])

        settlement = self._to_float(row[10])

        balance_before = self._to_float(row[11])

        balance_after = self._to_float(row[12])

        provider_fee = self._to_float(row[13])

        if amount == 0.0 and debit == 0.0 and not is_levy_line:

            # Phantom continuation row: pdfplumber occasionally
            # splits one logical transaction's wrapped date cell
            # into an extra one-row "table" with no real monetary
            # data (verified against the real statement - e.g. a
            # lone "00:12" date fragment with every other field
            # blank). Not a real transaction.

            return None

        direction = "out" if debit > 0 else "in"

        # ------------------------------------------------------
        # Build Transaction
        # ------------------------------------------------------

        transaction = {

            "date": raw_date,

            "amount": amount,

            "debit": debit,

            "net_settlement": settlement,

            "balance_before": balance_before,

            "balance_after": balance_after,

            "provider_fee": provider_fee,

            "direction": direction,

            "description": narration,

            "provider": provider,

            "service_type": service_type,

            "channel": "POS",

            "raw_observed_charge": provider_fee,

            "pricing_source": "statement",

            "parser_version": "2.0",

            "confidence": 0.99,

            "is_levy_line": is_levy_line,

            "is_emtl_qualifying": (

                service_type == "transfer_to_bank"
                and amount >= 10000
                and not is_levy_line

            ),

            "source": "table",

        }

        if self.debug:

            print(
                f"{raw_date} | "
                f"{provider:<12} | "
                f"{service_type:<18} | "
                f"₦{amount:,.2f} | "
                f"Fee: ₦{provider_fee:,.2f}"
            )

        return transaction

    # ==========================================================
    # TEXT EXTRACTION
    # ==========================================================

    def _extract_from_text(self):

        lines = self._read_text()

        if not lines:

            return []

        groups = self._build_transaction_groups(lines)

        if self.debug:

            print("\n" + "=" * 80)
            print("TEXT EXTRACTION")
            print("=" * 80)

            print(f"Lines Read          : {len(lines)}")
            print(f"Transaction Groups  : {len(groups)}")

        transactions = []

        for group in groups:

            txn = self._parse_text_group(group)

            if txn:

                transactions.append(txn)

        if self.debug:

            print(
                f"Text Transactions Parsed : "
                f"{len(transactions)}"
            )

        return transactions

    # ==========================================================
    # Read PDF as raw text
    # ==========================================================

    def _read_text(self):

        lines = []

        with pdfplumber.open(self.file_path) as pdf:

            for page in pdf.pages:

                text = page.extract_text()

                if not text:
                    continue

                for line in text.splitlines():

                    line = line.strip()

                    if line:

                        lines.append(line)

        if self.debug:

            print(
                f"\nRaw Text Lines : "
                f"{len(lines)}"
            )

        return lines

    # ==========================================================
    # Build transaction blocks
    # ==========================================================

    def _build_transaction_groups(self, lines):

        groups = []

        current = []

        for line in lines:

            upper = line.upper()

            # Ignore page headers
            if (
                "ACCOUNT STATEMENT" in upper
                or "ACCOUNT SUMMARY" in upper
                or "TRANSACTION DATE" in upper
            ):
                continue

            # A new transaction block starts at a line beginning
            # with a 4-digit year followed by a dash, e.g. "2026-".
            # Verified against real statement text: this is the
            # true block boundary. Narration markers like
            # "PURCHASE FOR" / "TRF" appear mid-block, not at the
            # start, and using them as the anchor causes each
            # block to swallow the following transaction's date
            # and amount fields.

            is_new = bool(re.match(r"^\d{4}-", line))

            if is_new:

                if current:

                    groups.append(current)

                current = [line]

                continue

            if current:

                current.append(line)

        if current:

            groups.append(current)

        return groups

    # ==========================================================
    # Parse one text transaction
    # ==========================================================

    def _parse_text_group(self, group):

        text = " ".join(group)

        upper = text.upper()

        # Detect accidental merge of two transactions.
        #
        # Previously this counted occurrences of "PURCHASE FOR" /
        # "POS_TRANSFER" / "TRF" in the block text. That produces
        # false positives on every genuine transfer, because a
        # single real TRF transaction legitimately contains "TRF"
        # twice (once as "TRF|..." in the data row, once as
        # "/TRF|..." in the narration line). Now that groups are
        # anchored on the date-line pattern, the correct signal
        # for a merge is more than one date-anchor line landing
        # in the same group.

        anchor_count = sum(

            1 for line in group if re.match(r"^\d{4}-", line)

        )

        if anchor_count > 1:

            if self.debug:

                print("\nMerged transaction detected\n")
                print(text[:500])

            return None

        service_type, is_levy_line = self._classify_service(upper)

        if service_type == "unknown":

            return None

        money = re.findall(

            r"\d{1,3}(?:,\d{3})*\.\d{2}",

            text,

        )

        if len(money) < 5:

            return None

        amount = self._to_float(money[0])

        debit = self._to_float(money[1])

        settlement = self._to_float(money[2])

        balance_before = self._to_float(money[3])

        balance_after = self._to_float(money[4])

        provider_fee = 0.0

        if len(money) >= 6:

            provider_fee = self._to_float(money[5])

        # ------------------------------------------------------
        # Date Extraction
        #
        # Each source line in this statement interleaves
        # fragments from multiple columns (date fragment + name
        # fragment + narration, all on one line), so date parts
        # like "2026-", "05-", "01T08:", "37:44" are NOT
        # contiguous in the space-joined `text` and cannot be
        # found by a single regex over it. Verified directly
        # against the real PDF: the date fragment is reliably the
        # FIRST whitespace-separated token of its line. Extract
        # those tokens in order and concatenate them.
        # ------------------------------------------------------

        date_fragment_patterns = (
            re.compile(r"^\d{4}-$"),
            re.compile(r"^\d{1,2}-$"),
            re.compile(r"^\d{1,2}T\d{1,2}:$"),
            re.compile(r"^\d{1,2}:\d{1,2}$"),
        )

        fragments = []

        for line in group:

            tokens = line.split()

            if not tokens:
                continue

            first_token = tokens[0]

            if any(
                pattern.match(first_token)
                for pattern in date_fragment_patterns
            ):

                fragments.append(first_token)

        raw_date = "".join(fragments)

        # Fallback: some rows render the trailing time fragment as
        # a bare 1-2 digit token with no colon (e.g. "19 -" instead
        # of "19:XX -") - the seconds component appears to be
        # genuinely absent from the extracted text in these cases,
        # not just missed by the patterns above. If we matched the
        # year/day/hour fragments but found no minute:second
        # fragment, check whether the group's last line starts
        # with a bare 1-2 digit number and use it as a minutes-only
        # value. We do NOT fabricate seconds here - if they aren't
        # in the source text, the date stays at HH:MM precision
        # rather than inventing ":00".

        has_minute_fragment = any(
            re.match(r"^\d{1,2}:\d{1,2}$", f) for f in fragments
        )

        if fragments and not has_minute_fragment and group:

            last_tokens = group[-1].split()

            if last_tokens and re.match(r"^\d{1,2}$", last_tokens[0]):

                raw_date += last_tokens[0]

        date = self._normalize_date(raw_date) if raw_date else ""

        description = text[:250]

        # Reject obviously bad parses

        if amount <= 0:
            return None

        if balance_after <= 0:
            return None

        if len(description) < 20:
            return None

        provider = self._detect_provider(upper)

        return {

            "date": date,

            "amount": amount,

            "debit": debit,

            "net_settlement": settlement,

            "balance_before": balance_before,

            "balance_after": balance_after,

            "provider_fee": provider_fee,

            "direction": "out" if debit > 0 else "in",

            "description": description,

            "provider": provider,

            "service_type": service_type,

            "channel": "POS",

            "raw_observed_charge": provider_fee,

            "pricing_source": "statement",

            "parser_version": "2.0",

            "confidence": 0.99,

            "is_levy_line": is_levy_line,

            "is_emtl_qualifying": (

                service_type == "transfer_to_bank"

                and amount >= 10000

                and not is_levy_line

            ),

            "source": "text",

        }

    # ==========================================================
    # Merge table and text transactions
    # ==========================================================

    def _merge_transactions(
        self,
        table_transactions,
        text_transactions,
    ):

        if self.debug:

            print("\n" + "=" * 80)
            print("MERGING RESULTS")
            print("=" * 80)

            print(
                f"Table Transactions : {len(table_transactions)}"
            )

            print(
                f"Text Transactions  : {len(text_transactions)}"
            )

        merged = {}

        for txn in table_transactions:

            key = self._transaction_key(txn)

            merged[key] = txn

        table_count = len(merged)

        duplicates = 0

        for txn in text_transactions:

            key = self._transaction_key(txn)

            if key not in merged:

                merged[key] = txn

            else:

                if self.debug:
                    print("Duplicate skipped:", key)

                duplicates += 1

        transactions = sorted(

            merged.values(),

            key=lambda x: x.get("date", "")

        )

        if self.debug:

            print()

            print(f"Duplicates Removed : {duplicates}")

            print(f"Unique Transactions : {len(transactions)}")

            print(
                f"Added from Text : "
                f"{len(transactions)-table_count}"
            )

        return transactions

    # ==========================================================
    # HELPERS
    # ==========================================================

    def _classify_service(self, upper, transaction_type=""):

        # Shared by both the table and text parsers, so both
        # pathways use one canonical service_type vocabulary.
        # This MUST match the vocabulary used everywhere else in
        # the codebase: validators.py's valid_service_types,
        # financial_engine.transaction_profit()'s if/elif chain,
        # providers/opay.py + providers/moniepoint.py's
        # _SERVICE_SCHEDULES keys, and the service_type strings
        # bootstrap.py seeds into the database ("withdrawal",
        # "purchase", "pos_transfer", "pos_qr", "transfer_to_bank").
        # An earlier version of this method used its own
        # cash_withdrawal/bank_transfer terms, which every one of
        # those other layers silently failed to recognize (the
        # validator coerced both down to "withdrawal", destroying
        # the withdrawal vs. bank-transfer distinction that EMTL/
        # Stamp Duty eligibility depends on). Previously the text
        # parser used a different vocabulary again and separately
        # had a `upper.startswith("TRF")` check that could never
        # match once groups were anchored on the date line instead
        # of the narration - "TRF" always appears mid-block now, so
        # that branch silently dropped every transfer. Using
        # "TRF|" in upper" instead of startswith fixes that, and
        # works for both parsers regardless of where in the block
        # the reference token appears.

        is_levy_line = False

        if "STAMP DUTY" in upper or "VALUE ADDED TAX" in upper:

            is_levy_line = True

            return "levy", is_levy_line

        if "PURCHASE FOR" in upper:

            return "withdrawal", is_levy_line

        if "POS_TRANSFER" in upper or "AP_TRSF" in upper:

            return "pos_transfer", is_levy_line

        if "TRF|" in upper or "TRANSFER COMPLETED" in upper or "TRANSFER TO" in upper:

            return "transfer_to_bank", is_levy_line

        # Fallback to the table's transaction_type column (blank
        # for text-sourced groups, since they have no such column)

        if transaction_type == "PURCHASE":

            return "withdrawal", is_levy_line

        if transaction_type == "POS_TRANSFER":

            return "pos_transfer", is_levy_line

        if transaction_type == "TRF":

            return "transfer_to_bank", is_levy_line

        return "unknown", is_levy_line

    def _detect_provider(self, upper):

        provider = "UNKNOWN"

        provider_patterns = {

            "OPAY": [
                "OPAY",
                "DIGITAL/OPAY",
            ],

            "MONIEPOINT": [
                "MONIEPOINT",
                "MONIEPOINT MFB",
            ],

            "PALMPAY": [
                "PALMPAY",
            ],

            "FIRST BANK": [
                "FIRST BANK",
            ],

            "UBA": [
                "UNITED BANK FOR AFRICA",
                " UBA ",
            ],

            "ACCESS": [
                "ACCESS BANK",
            ],

            "GTBANK": [
                "GTBANK",
                "GUARANTY TRUST",
            ],

            "ZENITH": [
                "ZENITH",
            ],

            "FCMB": [
                "FIRST CITY MONUMENT",
                "FCMB",
            ],

            "FIDELITY": [
                "FIDELITY",
            ],

            "UNION BANK": [
                "UNION BANK",
            ],

            "WEMA": [
                "WEMA",
            ],

            "STERLING": [
                "STERLING",
            ],

            "ECOBANK": [
                "ECOBANK",
            ],

            "KEYSTONE": [
                "KEYSTONE",
            ],

            "JAIZ": [
                "JAIZ",
            ],

            "KUDA": [
                "KUDA",
            ],

            "POLARIS": [
                "POLARIS",
                "POLARIS BANK",
            ],

        }

        for provider_name, aliases in provider_patterns.items():

            if any(alias in upper for alias in aliases):

                provider = provider_name

                break

        return provider

    def _normalize_date(self, raw):

        if not raw:
            return ""

        text = str(raw)

        # remove embedded newlines
        text = text.replace("\n", "")

        # 2026-05-01T08:37:44
        text = text.replace("T", " ")

        # remove duplicate spaces
        text = re.sub(r"\s+", " ", text)

        # extract proper datetime
        m = re.search(
            r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}",
            text
        )

        if m:
            return m.group(0)

        return text.strip()

    def _to_float(self, value):

        try:
            return float(str(value).replace(",", ""))

        except Exception:
            return 0.0

    # ==========================================================
    # Confidence Score
    # ==========================================================

    def _calculate_confidence(
        self,
        transactions,
    ):

        if not transactions:

            return 0.0

        score = 0.50

        score += min(
            len(transactions) / 40,
            1.0
        ) * 0.25

        table_count = sum(

            1

            for t in transactions

            if t.get("source") == "table"

        )

        score += min(

            table_count / 20,

            1.0

        ) * 0.15

        dated = sum(

            1

            for t in transactions

            if t.get("date")

        )

        score += min(

            dated / len(transactions),

            1.0

        ) * 0.10

        return round(score, 2)

    # ==========================================================
    # Transaction Key
    # ==========================================================

    def _transaction_key(
        self,
        txn,
    ):

        amount = round(
            txn.get("amount", 0),
            2,
        )

        date = txn.get(
            "date",
            "",
        )

        provider_fee = round(
            txn.get("provider_fee", 0),
            2,
        )

        direction = txn.get(
            "direction",
            "",
        )

        return (
            date,
            amount,
            provider_fee,
            direction,
        )

    def _failure(self, errors):

        return {

            "success": False,

            "transaction_count": 0,

            "transactions": [],

            "confidence_score": 0.0,

            "errors": errors,

            "provider": "Moniepoint",

            "source_format": "pdf",

        }