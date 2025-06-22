import sqlite3
import streamlit as st
import pandas as pd
from datetime import datetime
import openpyxl
import io

# --- App content ---strea,m
st.set_page_config(layout="centered")

# Database connection
conn = sqlite3.connect("accounting.db", check_same_thread=False)
c = conn.cursor()

# Create tables
def create_tables():
    c.execute('''CREATE TABLE IF NOT EXISTS chart_of_accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT,
                    level INTEGER,
                    parent_id INTEGER
                )''')

    c.execute('''CREATE TABLE IF NOT EXISTS vouchers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT,
                    description TEXT
                )''')

    c.execute('''CREATE TABLE IF NOT EXISTS voucher_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    voucher_id INTEGER,
                    account_id INTEGER,
                    debit REAL,
                    credit REAL,
                    FOREIGN KEY(voucher_id) REFERENCES vouchers(id),
                    FOREIGN KEY(account_id) REFERENCES chart_of_accounts(id)
                )''')

    conn.commit()
create_tables()

# User credentials
users = {
    "admin": "admin123",
    "user1": "password1"
}

# Login screen
def login():
    st.title("Login")
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")
        if submitted:
            if username in users and users[username] == password:
                st.session_state["authenticated"] = True
                st.session_state["username"] = username
                st.success(f"Welcome, {username}!")
                st.rerun()
            else:
                st.error("Invalid username or password")

# Initialize login state
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

# Show login page or main app
if not st.session_state["authenticated"]:
    login()
    st.stop()

# Logout button
st.sidebar.write(f"Logged in as: {st.session_state['username']}")
if st.sidebar.button("Logout"):
    st.session_state["authenticated"] = False
    st.rerun()

#chart of account tab
def chart_of_accounts():
    st.header("Chart of Accounts")

    # Fetch accounts from the database
    accounts_df = pd.read_sql("SELECT * FROM chart_of_accounts", conn)

    # Separate accounts by level
    level_1_accounts = accounts_df[accounts_df['level'] == 1]
    level_2_accounts = accounts_df[accounts_df['level'] == 2]

    # Move Level selection outside form to allow dynamic UI updates
    level = st.selectbox("Select Account Level", [1, 2, 3])

    with st.form("Add Account"):
        name = st.text_input("Account Name")

        parent_id = None

        if level == 1:
            st.markdown("**Parent Account:** Top-level (no parent)")
            parent_id = 0

        elif level == 2:
            if not level_1_accounts.empty:
                selected = st.selectbox(
                    "Select Parent Account (Level 1)",
                    level_1_accounts['name'].tolist()
                )
                parent_id = level_1_accounts[level_1_accounts['name'] == selected]['id'].values[0]
            else:
                st.warning("No Level 1 accounts available. Please add one first.")
                return

        elif level == 3:
            if not level_2_accounts.empty:
                selected = st.selectbox(
                    "Select Parent Account (Level 2)",
                    level_2_accounts['name'].tolist()
                )
                parent_id = level_2_accounts[level_2_accounts['name'] == selected]['id'].values[0]
            else:
                st.warning("No Level 2 accounts available. Please add one first.")
                return

        submitted = st.form_submit_button("Add Account")
        if submitted:
            c.execute("INSERT INTO chart_of_accounts (name, level, parent_id) VALUES (?, ?, ?)",
                      (name, level, parent_id if parent_id != 0 else None))
            conn.commit()
            st.success("Account added successfully")

    st.subheader("Existing Accounts")
    st.dataframe(accounts_df)

# Vouchers
def vouchers():
    st.header("Vouchers")

    # Get next voucher serial number
    last_voucher = pd.read_sql("SELECT MAX(id) as max_id FROM vouchers", conn)
    next_voucher_id = (last_voucher['max_id'][0] or 0) + 1
    st.markdown(f"**Voucher Serial Number:** {next_voucher_id}")

    # Get only Level 3 accounts for dropdown
    accounts = pd.read_sql("SELECT id, name FROM chart_of_accounts WHERE level = 3", conn)
    account_dict = dict(zip(accounts['id'], accounts['name']))

    with st.form("Add Voucher", clear_on_submit=True):  # Ensures form resets on submit
        date = st.date_input("Date", datetime.today())
        description = st.text_input("Description")

        entries = []
        for i in range(5):
            col1, col2, col3 = st.columns(3)
            with col1:
                acc_id = st.selectbox(
                    f"Account {i+1}",
                    options=[0] + list(account_dict.keys()),
                    format_func=lambda x: account_dict.get(x, "Select Account"),
                    key=f"acc_{i}"
                )
            with col2:
                debit = st.number_input(f"Debit {i+1}", min_value=0.0, value=0.0, key=f"debit_{i}")
            with col3:
                credit = st.number_input(f"Credit {i+1}", min_value=0.0, value=0.0, key=f"credit_{i}")

            if acc_id and acc_id != 0:
                entries.append((acc_id, debit, credit))

        if st.form_submit_button("Save Voucher"):
            total_debit = sum(x[1] for x in entries)
            total_credit = sum(x[2] for x in entries)
            if total_debit == total_credit and total_debit > 0:
                # Save main voucher
                c.execute("INSERT INTO vouchers (date, description) VALUES (?, ?)",
                          (date.strftime("%Y-%m-%d"), description))
                voucher_id = c.lastrowid

                # Save voucher line entries
                for acc_id, debit, credit in entries:
                    if debit > 0 or credit > 0:
                        c.execute("INSERT INTO voucher_entries (voucher_id, account_id, debit, credit) VALUES (?, ?, ?, ?)",
                                  (voucher_id, acc_id, debit, credit))
                conn.commit()
                st.success(f"Voucher #{voucher_id} saved successfully")
            else:
                st.error("Total Debit and Credit must be equal and greater than zero")

    # Optional: show recent vouchers
    st.subheader("Recent Vouchers")
    voucher_data = pd.read_sql("""
        SELECT v.id as Voucher_ID, v.date, v.description, c.name as Account, ve.debit, ve.credit
        FROM vouchers v
        JOIN voucher_entries ve ON v.id = ve.voucher_id
        JOIN chart_of_accounts c ON ve.account_id = c.id
        ORDER BY v.id DESC LIMIT 10
    """, conn)
    st.dataframe(voucher_data)


# Ledger
def ledger():
    st.header("Ledger")

    # Fetch Level 3 accounts
    accounts_df = pd.read_sql("SELECT id, name FROM chart_of_accounts WHERE level = 3", conn)
    account_options = ["All"] + accounts_df['name'].tolist()
    account_name_to_id = {row['name']: row['id'] for _, row in accounts_df.iterrows()}
    account_id_to_name = {v: k for k, v in account_name_to_id.items()}

    selected_account = st.selectbox("Select Account", options=account_options)
    from_date = st.date_input("From Date", key="ledger_from")
    to_date = st.date_input("To Date", key="ledger_to")

    if st.button("Show Ledger"):
        output = io.BytesIO()

        if selected_account == "All":
            full_ledger = pd.DataFrame()

            for acc_id, acc_name in account_id_to_name.items():
                # Opening balance
                opening = pd.read_sql('''
                    SELECT SUM(ve.debit) as total_debit, SUM(ve.credit) as total_credit
                    FROM voucher_entries ve
                    JOIN vouchers v ON ve.voucher_id = v.id
                    WHERE ve.account_id = ? AND date(v.date) < ?
                ''', conn, params=(acc_id, from_date))

                opening_balance = (opening['total_debit'][0] or 0) - (opening['total_credit'][0] or 0)

                # Transactions
                txns = pd.read_sql('''
                    SELECT ve.voucher_id, v.date, v.description, ve.debit, ve.credit
                    FROM voucher_entries ve
                    JOIN vouchers v ON ve.voucher_id = v.id
                    WHERE ve.account_id = ? AND date(v.date) BETWEEN ? AND ?
                    ORDER BY v.date
                ''', conn, params=(acc_id, from_date, to_date))

                # Opening row
                opening_row = pd.DataFrame([{
                    'voucher_id': None,
                    'date': from_date.strftime('%Y-%m-%d'),
                    'description': 'Opening Balance',
                    'debit': 0.0,
                    'credit': 0.0,
                    'balance': opening_balance
                }])

                # Calculate balance & running balance
                if not txns.empty:
                    txns['balance'] = txns['debit'] - txns['credit']
                else:
                    txns['balance'] = []

                df = pd.concat([opening_row, txns], ignore_index=True)
                df['running_balance'] = df['balance'].cumsum()
                df['account_name'] = acc_name

                full_ledger = pd.concat([full_ledger, df], ignore_index=True)

            # Reorder columns
            full_ledger = full_ledger[['account_name', 'voucher_id', 'date', 'description', 'debit', 'credit', 'balance', 'running_balance']]
            st.dataframe(full_ledger)

            # Export all ledgers to Excel
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                full_ledger.to_excel(writer, index=False, sheet_name='All Ledgers')

            st.download_button(
                "Download All Ledgers as Excel",
                data=output.getvalue(),
                file_name="all_ledgers.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        else:
            account_id = account_name_to_id[selected_account]

            # Single account logic (same as before)
            opening = pd.read_sql('''
                SELECT SUM(ve.debit) as total_debit, SUM(ve.credit) as total_credit
                FROM voucher_entries ve
                JOIN vouchers v ON ve.voucher_id = v.id
                WHERE ve.account_id = ? AND date(v.date) < ?
            ''', conn, params=(account_id, from_date))

            opening_balance = (opening['total_debit'][0] or 0) - (opening['total_credit'][0] or 0)

            txns = pd.read_sql('''
                SELECT ve.voucher_id, v.date, v.description, ve.debit, ve.credit
                FROM voucher_entries ve
                JOIN vouchers v ON ve.voucher_id = v.id
                WHERE ve.account_id = ? AND date(v.date) BETWEEN ? AND ?
                ORDER BY v.date
            ''', conn, params=(account_id, from_date, to_date))

            opening_row = pd.DataFrame([{
                'voucher_id': None,
                'date': from_date.strftime('%Y-%m-%d'),
                'description': 'Opening Balance',
                'debit': 0.0,
                'credit': 0.0,
                'balance': opening_balance
            }])

            if not txns.empty:
                txns['balance'] = txns['debit'] - txns['credit']
            else:
                txns['balance'] = []

            df = pd.concat([opening_row, txns], ignore_index=True)
            df['running_balance'] = df['balance'].cumsum()
            df['account_name'] = selected_account
            df = df[['voucher_id', 'date', 'description', 'account_name', 'debit', 'credit', 'balance', 'running_balance']]

            st.dataframe(df)

            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='Ledger')

            st.download_button(
                "Download Ledger as Excel",
                data=output.getvalue(),
                file_name="ledger.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )





# Trial Balance
def trial_balance():
    st.header("Trial Balance")
    from_date = st.date_input("From Date", key="tb_from")
    to_date = st.date_input("To Date", key="tb_to")

    if st.button("Show Trial Balance"):
        query = '''
            SELECT co.name AS account_name,
                   SUM(ve.debit) AS total_debit,
                   SUM(ve.credit) AS total_credit
            FROM voucher_entries ve
            JOIN vouchers v ON ve.voucher_id = v.id
            JOIN chart_of_accounts co ON ve.account_id = co.id
            WHERE date(v.date) BETWEEN ? AND ?
            GROUP BY ve.account_id
        '''

        df = pd.read_sql(query, conn, params=(from_date, to_date))
        df['balance'] = df['total_debit'] - df['total_credit']
        st.dataframe(df)

        st.write("**Total Debit:**", df['total_debit'].sum())
        st.write("**Total Credit:**", df['total_credit'].sum())

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Trial Balance')
        st.download_button("Download Trial Balance as Excel", data=output.getvalue(), file_name="trial_balance.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# Tab Layout
tabs = st.tabs(["Chart of Accounts", "Vouchers", "Ledger", "Trial Balance"])
with tabs[0]: chart_of_accounts()
with tabs[1]: vouchers()
with tabs[2]: ledger()
with tabs[3]: trial_balance()

