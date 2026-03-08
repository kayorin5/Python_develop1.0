import os
import glob
import datetime
import unicodedata
import pandas as pd


def is_emoji(ch: str) -> bool:
    if not ch:
        return False
    cp = ord(ch)
    return any(
        start <= cp <= end
        for (start, end) in [
            (0x1F600, 0x1F64F),
            (0x1F300, 0x1F5FF),
            (0x1F680, 0x1F6FF),
            (0x2600, 0x26FF),
            (0x2700, 0x27BF),
            (0x1F1E6, 0x1F1FF),
            (0x1F900, 0x1F9FF),
            (0x1FA70, 0x1FAFF),
            (0x200D, 0x200D),
        ]
    )


def replace_bad_chars(text: str) -> str:
    if pd.isna(text):
        return text
    out_chars = []
    for ch in str(text):
        cat = unicodedata.category(ch)
        if is_emoji(ch) or cat in ("Cc", "Cs"):
            out_chars.append("_")
        else:
            out_chars.append(ch)
    return "".join(out_chars)


def is_split_candidate(ch: str) -> bool:
    """絵文字、記号、句読点を分割候補とする"""
    if is_emoji(ch):
        return True
    cat = unicodedata.category(ch)
    if cat.startswith("P") or cat.startswith("S"):
        return True
    return False


def _char_display_width(ch: str) -> float:
    """全角換算幅: 全角/幅の広い文字は1、その他は0.5を返す"""
    return 1.0 if unicodedata.east_asian_width(ch) in ("F", "W") else 0.5


def split_text_by_rules(text: str) -> tuple[str, str]:
    """テキストを規則に従い前半と残りに分割する。

    - 全角換算で50文字目以降に、絵文字または記号/句読点が出現したらその文字で分割（その文字は前半に含める）。
    - 該当がなければ前半に全体、残りは空文字。
    """
    if pd.isna(text) or text == "":
        return "", ""
    s = str(text)
    cum = 0.0
    for i, ch in enumerate(s):
        cum += _char_display_width(ch)
        if cum >= 50.0 and is_split_candidate(ch):
            return s[: i + 1], s[i + 1 :]
    return s, ""


def read_csv_try_encodings(path: str) -> pd.DataFrame:
    encodings = ["utf-8", "utf-8-sig", "cp932", "shift_jis"]
    for enc in encodings:
        try:
            return pd.read_csv(path, header=None, encoding=enc, dtype=str, keep_default_na=False)
        except Exception:
            continue
    # last resort: read with errors replaced
    return pd.read_csv(path, header=None, encoding="utf-8", dtype=str, errors="replace", keep_default_na=False)


def process_file(path: str, out_dir: str) -> pd.DataFrame:
    df = read_csv_try_encodings(path)
    # select columns by index: 1,2,4,6,7 (2,3,4,7,8 in 1-based)
    cols_idx = [1, 2, 4, 6, 7]
    max_idx = df.shape[1] - 1
    selected = []
    for idx in cols_idx:
        if idx <= max_idx:
            selected.append(df.iloc[:, idx].astype(str))
        else:
            # create empty column if missing
            selected.append(pd.Series([""] * len(df)))
    out_df = pd.concat(selected, axis=1)
    out_df.columns = ["datetime", "text", "imp", "rt", "likes"]

    # For combined Excel we keep original text, so return this dataframe
    combined_df = out_df.copy()
    # add データ名 column derived from filename (text in brackets)
    base = os.path.basename(path)
    name, ext = os.path.splitext(base)
    member = name.split("_", 1)[0] if "_" in name else name
    combined_df["データ名"] = f"[{member}]"

    # split text into 前半 and 残り according to the rule, place 残り in a new column to the right
    heads = []
    tails = []
    for t in combined_df["text"]:
        h, ta = split_text_by_rules(t)
        heads.append(h)
        tails.append(ta)
    combined_df["text"] = heads
    # insert tail column immediately to the right of `text`
    try:
        text_pos = combined_df.columns.get_loc("text")
    except Exception:
        text_pos = 1
    combined_df.insert(text_pos + 1, "text_tail", tails)

    # split datetime into 投稿年月 and 投稿時間
    yms = []
    times = []
    for t in combined_df["datetime"]:
        if pd.isna(t) or str(t).strip() == "":
            yms.append("")
            times.append("")
            continue
        ts = pd.to_datetime(t, errors="coerce")
        if not pd.isna(ts):
            yms.append(ts.strftime("%Y-%m-%d"))
            times.append(ts.strftime("%H:%M:%S"))
        else:
            parts = str(t).split()
            if len(parts) >= 2:
                yms.append(parts[0][:7])
                times.append(parts[1])
            else:
                yms.append(parts[0] if parts else "")
                times.append("")

    # replace datetime column with 投稿年月 and insert 投稿時間 next to it
    try:
        dt_pos = combined_df.columns.get_loc("datetime")
    except Exception:
        dt_pos = 0
    combined_df.iloc[:, dt_pos] = yms
    combined_df.rename(columns={"datetime": "投稿年月日"}, inplace=True)
    combined_df.insert(dt_pos + 1, "投稿時間", times)

    # For fixed CSV, replace emojis and control/surrogate characters in text
    fixed_df = out_df.copy()
    fixed_df["text"] = fixed_df["text"].apply(replace_bad_chars)

    base = os.path.basename(path)
    name, ext = os.path.splitext(base)
    out_name = f"{name}_fixed.csv"
    out_path = os.path.join(out_dir, out_name)
    # write CSV with BOM for Excel compatibility on Windows
    fixed_df.to_csv(out_path, index=False, header=False, encoding="utf-8-sig")
    return combined_df


def main(root_dir: str):
    # only process CSV files under the `csvdata` directory
    csv_dir = os.path.join(root_dir, "csvdata")
    if not os.path.isdir(csv_dir):
        print("No csvdata directory found.")
        return
    pattern = os.path.join(csv_dir, "**", "*.csv")
    files = glob.glob(pattern, recursive=True)
    files = [f for f in files if not f.endswith("_fixed.csv")]
    files = [f for f in files if "ikizulive_" not in os.path.basename(f)]

    if not files:
        print("No CSV files found.")
        return

    # decide output directory: default is csv_dir; if multiple files, create dated folder
    today = datetime.datetime.now().strftime("%Y%m%d")
    if len(files) > 1:
        target_dir = os.path.join(csv_dir, today)
        os.makedirs(target_dir, exist_ok=True)
    else:
        target_dir = csv_dir

    combined_list = []
    for p in files:
        try:
            combined = process_file(p, target_dir)
            # if not the first file, drop the first row before appending
            if combined_list:
                combined = combined.iloc[1:].reset_index(drop=True)
            combined_list.append(combined)
            print(f"Processed: {p}")
        except Exception as e:
            print(f"Failed processing {p}: {e}")

    if combined_list:
        all_df = pd.concat(combined_list, ignore_index=True)
        out_xlsx = os.path.join(target_dir, f"ikizulive_{today}.xlsx")
        # Treat first row of the first input file as header row.
        orig_header_row = all_df.iloc[0].tolist()
        data_df = all_df.iloc[1:].reset_index(drop=True)

        # Build header labels based on dataframe column names and original first-row values.
        header_labels = []
        cols = all_df.columns.tolist()
        for col, orig in zip(cols, orig_header_row):
            if col == "投稿年月日":
                header_labels.append("投稿年月日")
            elif col == "投稿時間":
                header_labels.append("投稿時間")
            elif col == "データ名":
                header_labels.append("メンバー名")
            else:
                header_labels.append(orig if orig != "" else col)

        # pad if necessary
        if len(header_labels) < data_df.shape[1]:
            header_labels += [""] * (data_df.shape[1] - len(header_labels))

        data_df.columns = header_labels
        # write with header row
        data_df.to_excel(out_xlsx, index=False, header=True)
        print(f"Combined Excel written: {out_xlsx}")


if __name__ == "__main__":
    root = os.path.dirname(os.path.abspath(__file__))
    main(root)
