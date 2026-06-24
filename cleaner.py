import pandas as pd

def clean_data(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # Type and Amount are already normalized by data_loader (synonyms mapped,
    # currency symbols stripped) — unrecognized/unparsable values come through
    # as None/NaN here and get dropped, with the user already warned about why.
    df = df.dropna(subset=['Date', 'Amount', 'Type'])
    df['Category'] = df['Category'].fillna('Uncategorized')
    df['Description'] = df['Description'].fillna('No description')
    df = df[df['Amount'] > 0]
    df = df[df['Type'].isin(['Revenue', 'Expense'])]  # defense in depth
    df = df.sort_values('Date').reset_index(drop=True)
    return df
