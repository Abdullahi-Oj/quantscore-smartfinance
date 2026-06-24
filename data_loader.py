import re
import pandas as pd
import streamlit as st

REQUIRED_COLUMNS = ['Date', 'Description', 'Category', 'Type', 'Amount']

# Common real-world ways an SME owner types these in, beyond the exact
# "Revenue"/"Expense" the template asks for.
REVENUE_SYNONYMS = {'revenue', 'income', 'sales', 'sale', 'credit', 'earning', 'earnings', 'receipt', 'receipts'}
EXPENSE_SYNONYMS = {'expense', 'expenses', 'cost', 'costs', 'spending', 'debit', 'payment', 'payments', 'outflow', 'outgoing'}

_CURRENCY_NOISE = re.compile(r'[₦$,\s]|ngn', re.IGNORECASE)


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Matches headers case-insensitively and ignoring stray whitespace
    ('date', ' Type', 'amount ' etc.) onto the canonical required names,
    instead of failing the whole file over a header typo or trailing space."""
    rename_map = {}
    for col in df.columns:
        stripped = str(col).strip()
        for required in REQUIRED_COLUMNS:
            if stripped.lower() == required.lower() and col != required:
                rename_map[col] = required
                break
    return df.rename(columns=rename_map) if rename_map else df


def _clean_amount(value):
    """Strips currency symbols/commas/whitespace before parsing, instead of
    letting pd.to_numeric silently fail and turn '₦250,000' into 0."""
    if pd.isna(value):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = _CURRENCY_NOISE.sub('', str(value))
    try:
        return float(text)
    except ValueError:
        return None


def _normalize_type(value):
    """Accepts common synonyms (Income/Sales -> Revenue, Cost/Debit -> Expense)
    case-insensitively, instead of silently dropping anything that isn't an
    exact 'Revenue'/'Expense' match."""
    if pd.isna(value):
        return None
    text = str(value).strip().lower()
    if text in REVENUE_SYNONYMS:
        return 'Revenue'
    if text in EXPENSE_SYNONYMS:
        return 'Expense'
    return None


def load_data(file_path_or_buffer) -> pd.DataFrame:
    if hasattr(file_path_or_buffer, "seek"):
        file_path_or_buffer.seek(0)
    try:
        df = pd.read_excel(file_path_or_buffer, engine="openpyxl")
    except Exception as e:
        st.error(f"❌ Could not read file: {e}")
        return None

    df = _normalize_columns(df)

    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        st.error(f"❌ Missing required columns: {', '.join(missing)}")
        return None

    # Dates: standard parse, then retry failures as day-first (DD-MM-YYYY is
    # the common manual-entry convention in Nigeria) before giving up on them.
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    still_missing = df['Date'].isna()
    if still_missing.any():
        retried = pd.to_datetime(df.loc[still_missing, 'Date'], errors='coerce', dayfirst=True)
        df.loc[still_missing, 'Date'] = retried
    invalid_dates = df['Date'].isna().sum()
    if invalid_dates > 0:
        st.warning(f"⚠️ {invalid_dates} row(s) have unreadable dates and will be skipped.")
        df = df.dropna(subset=['Date'])

    # Amounts: parse robustly, and SURFACE failures instead of silently
    # zeroing them out (a zeroed Revenue row would otherwise vanish into
    # the totals without anyone noticing the number is wrong).
    parsed_amount = df['Amount'].apply(_clean_amount)
    parsed_amount = pd.to_numeric(parsed_amount, errors='coerce')  # force real numeric dtype;
    # without this, an all-unparseable column can infer as a non-numeric
    # (Arrow-string-backed) dtype that .abs() below can't operate on at all.
    unparsable = parsed_amount.isna() & df['Amount'].notna()
    if unparsable.any():
        st.warning(
            f"⚠️ {unparsable.sum()} row(s) have an Amount that couldn't be read as a number "
            f"and will be skipped. Check for stray text or symbols in the Amount column."
        )
    df['Amount'] = parsed_amount.abs()  # sign comes from the Type column, not the raw figure

    # Type: accept synonyms, and SURFACE anything still unrecognized instead
    # of silently dropping it.
    normalized_type = df['Type'].apply(_normalize_type)
    unrecognized = normalized_type.isna() & df['Type'].notna()
    if unrecognized.any():
        bad_values = sorted(set(df.loc[unrecognized, 'Type'].astype(str)))
        preview = ', '.join(bad_values[:5]) + ('...' if len(bad_values) > 5 else '')
        st.warning(
            f"⚠️ {unrecognized.sum()} row(s) have a Type value SmartFinance doesn't recognize "
            f"({preview}) and will be skipped. Use 'Revenue' or 'Expense' "
            f"(Income/Sales and Cost/Debit are also accepted)."
        )
    df['Type'] = normalized_type

    df['Month'] = df['Date'].dt.to_period('M')
    df['MonthLabel'] = df['Date'].dt.strftime('%b %Y')

    return df
