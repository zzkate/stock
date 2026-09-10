#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт расчёта подневных товарных остатков на основе помесячных данных товародвижения.

Входные данные:
  - Файлы товародвижения: .../invent_trans/invent_trans_YYYY_MM.csv
    Формат: item_id;location_id;trans_date;qty;cost_amount
    Отрицательные qty - расходная операция, положительные - приходная операция

  - Файлы остатков: .../stock/stock_YYYY_MM_DD.csv
    Формат: item_id;location_id;trans_date;qty;cost_amount
    qty и cost_amount - остаток на конец дня trans_date

Выходные данные:
  - Файлы stock_YYYY_MM_DD.csv в папке stock/

Метод расчёта себестоимости: средневзвешенная стоимость (weighted average cost)
  new_cost = (old_qty * old_cost + trans_qty * trans_cost) / new_qty
"""

import csv
import os
import sys
from datetime import datetime, timedelta
from collections import defaultdict
import glob


def parse_date(date_str):
    """Parse YYYY-MM-DD string to date object."""
    return datetime.strptime(date_str, '%Y-%m-%d').date()


def format_date(date_obj):
    """Format date object to YYYY-MM-DD string."""
    return date_obj.strftime('%Y-%m-%d')


def read_trans_file(filepath):
    """
    Read inventory transaction file.

    Args:
        filepath: Path to CSV file

    Returns:
        List of dicts with keys: item_id, location_id, trans_date, qty, cost_amount
    """
    transactions = []
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            transactions.append({
                'item_id': row['item_id'],
                'location_id': row['location_id'],
                'trans_date': parse_date(row['trans_date']),
                'qty': float(row['qty']),
                'cost_amount': float(row['cost_amount'])
            })
    return transactions


def read_stock_file(filepath):
    """
    Read stock balance file.

    Args:
        filepath: Path to CSV file

    Returns:
        Dict: (item_id, location_id) -> {trans_date, qty, cost_amount}
    """
    stock = {}
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            key = (row['item_id'], row['location_id'])
            stock[key] = {
                'trans_date': parse_date(row['trans_date']),
                'qty': float(row['qty']),
                'cost_amount': float(row['cost_amount'])
            }
    return stock


def write_stock_file(filepath, stock_data):
    """
    Write stock balance to CSV file.

    Args:
        filepath: Output file path
        stock_data: List of dicts with keys: item_id, location_id, trans_date, qty, cost_amount
    """
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w', encoding='utf-8', newline='') as f:
        fieldnames = ['item_id', 'location_id', 'trans_date', 'qty', 'cost_amount']
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=';')
        writer.writeheader()
        for row in sorted(stock_data, key=lambda x: (x['item_id'], x['location_id'], x['trans_date'])):
            # Format numbers: use '.' as decimal separator, trim trailing zeros
            qty_str = f"{row['qty']:.6f}".rstrip('0').rstrip('.')
            cost_str = f"{row['cost_amount']:.6f}".rstrip('0').rstrip('.')
            writer.writerow({
                'item_id': row['item_id'],
                'location_id': row['location_id'],
                'trans_date': format_date(row['trans_date']),
                'qty': qty_str,
                'cost_amount': cost_str
            })


def load_all_transactions(trans_dir, start_date, end_date):
    """
    Load all transactions from monthly files within date range.

    Args:
        trans_dir: Directory containing invent_trans_YYYY_MM.csv files
        start_date: Start of date range (inclusive)
        end_date: End of date range (inclusive)

    Returns:
        List of transaction dicts
    """
    all_transactions = []
    pattern = os.path.join(trans_dir, 'invent_trans_*.csv')

    for filepath in glob.glob(pattern):
        transactions = read_trans_file(filepath)
        for trans in transactions:
            if start_date <= trans['trans_date'] <= end_date:
                all_transactions.append(trans)

    return all_transactions


def calculate_daily_stock(transactions, initial_stock, start_date, end_date):
    """
    Calculate daily stock balances using weighted average cost method.

    Args:
        transactions: List of transaction dicts
        initial_stock: Dict (item_id, location_id) -> {qty, cost_amount}
                       as of day before start_date
        start_date: First date to calculate
        end_date: Last date to calculate

    Returns:
        List of stock dicts for each day
    """
    # Group transactions by date
    trans_by_date = defaultdict(list)
    for trans in transactions:
        if start_date <= trans['trans_date'] <= end_date:
            trans_by_date[trans['trans_date']].append(trans)

    # Initialize current stock from initial
    current_stock = {}
    for key, data in initial_stock.items():
        current_stock[key] = {'qty': data['qty'], 'cost_amount': data['cost_amount']}

    # Track all item/location combinations
    all_keys = set(initial_stock.keys())
    for trans in transactions:
        if start_date <= trans['trans_date'] <= end_date:
            all_keys.add((trans['item_id'], trans['location_id']))

    daily_stock = []
    current_date = start_date

    while current_date <= end_date:
        # Apply transactions for this date
        if current_date in trans_by_date:
            for trans in trans_by_date[current_date]:
                key = (trans['item_id'], trans['location_id'])
                if key not in current_stock:
                    current_stock[key] = {'qty': 0.0, 'cost_amount': 0.0}

                old_qty = current_stock[key]['qty']
                old_cost = current_stock[key]['cost_amount']

                # Update quantity (positive = income, negative = expense)
                new_qty = old_qty + trans['qty']
                current_stock[key]['qty'] = new_qty

                # Update cost using weighted average cost method
                # Formula: new_cost = (old_qty * old_cost + trans_qty * trans_cost) / new_qty
                if new_qty != 0:
                    new_cost = (old_qty * old_cost + trans['qty'] * trans['cost_amount']) / new_qty
                    current_stock[key]['cost_amount'] = new_cost
                else:
                    # Quantity became zero
                    current_stock[key]['cost_amount'] = 0.0

        # Record stock for this date
        for key in all_keys:
            if key in current_stock:
                daily_stock.append({
                    'item_id': key[0],
                    'location_id': key[1],
                    'trans_date': current_date,
                    'qty': current_stock[key]['qty'],
                    'cost_amount': current_stock[key]['cost_amount']
                })

        current_date += timedelta(days=1)

    return daily_stock


def find_latest_stock_file(stock_dir, before_date=None):
    """
    Find the most recent stock file in the directory.

    Args:
        stock_dir: Directory containing stock_YYYY_MM_DD.csv files
        before_date: Optional date - only consider files before this date

    Returns:
        Path to the latest stock file, or None if not found
    """
    pattern = os.path.join(stock_dir, 'stock_*.csv')
    latest_file = None
    latest_date = None

    for filepath in glob.glob(pattern):
        # Extract date from filename: stock_YYYY_MM_DD.csv
        filename = os.path.basename(filepath)
        try:
            date_str = filename.replace('stock_', '').replace('.csv', '')
            file_date = datetime.strptime(date_str, '%Y_%m_%d').date()

            print("file_date = ", file_date)

            if before_date and file_date >= before_date:
                continue

            if latest_date is None or file_date > latest_date:
                latest_date = file_date
                latest_file = filepath
        except ValueError:
            continue

    return latest_file


def main():
    """Main entry point."""
    # Configuration - adjust these paths as needed
    trans_dir = 'invent_trans'
    stock_dir = 'stock'

    # Date range for calculation
    # Example: calculate for July 2025
    start_date = parse_date('2025-07-01')
    end_date = parse_date('2025-07-31')

    # Find the latest stock file before start_date to use as initial balance
    initial_stock_file = find_latest_stock_file(stock_dir, before_date=start_date)

    if not initial_stock_file:
        print(f"Error: No stock file found in {stock_dir} before {start_date}")
        sys.exit(1)

    print(f"Using initial stock from: {initial_stock_file}")

    # Load initial stock
    initial_stock = read_stock_file(initial_stock_file)
    print(f"Loaded {len(initial_stock)} item/location combinations from initial stock")

    # Load all transactions within date range
    transactions = load_all_transactions(trans_dir, start_date, end_date)
    print(f"Loaded {len(transactions)} transactions from {start_date} to {end_date}")

    # Calculate daily stock
    daily_stock = calculate_daily_stock(transactions, initial_stock, start_date, end_date)
    print(f"Calculated {len(daily_stock)} daily stock records")

    # Group by date and write output files
    stock_by_date = defaultdict(list)
    for record in daily_stock:
        stock_by_date[record['trans_date']].append(record)

    for date, records in sorted(stock_by_date.items()):
        filepath = os.path.join(stock_dir, f"stock_{format_date(date)}.csv")
        write_stock_file(filepath, records)
        print(f"Written {filepath} ({len(records)} records)")

    print("\nDone!")


if __name__ == '__main__':
    main()
