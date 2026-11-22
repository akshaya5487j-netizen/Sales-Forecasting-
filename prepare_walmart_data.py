import pandas as pd

# Load the Walmart dataset
df = pd.read_csv('Walmart.csv')

print(f"Original data: {len(df)} rows, {len(df.columns)} columns")
print(f"Columns: {df.columns.tolist()}")

# Convert date and aggregate weekly sales by date
df['Date'] = pd.to_datetime(df['Date'], format='%d-%m-%Y')

# Group by date and sum weekly sales across all stores
sales_data = df.groupby('Date')['Weekly_Sales'].sum().reset_index()
sales_data.columns = ['Date', 'Sales']

# Sort by date
sales_data = sales_data.sort_values('Date')

print(f"\nPrepared data: {len(sales_data)} rows")
print(f"Date range: {sales_data['Date'].min()} to {sales_data['Date'].max()}")
print(f"\nFirst 5 rows:")
print(sales_data.head())

# Save prepared data
output_file = 'walmart_prepared.csv'
sales_data.to_csv(output_file, index=False)
print(f"\n✅ Saved to: {output_file}")
print("\nNow upload 'walmart_prepared.csv' to the forecasting tool!")
