from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for
import pandas as pd
import numpy as np
from prophet import Prophet
import plotly
import json
import os
from werkzeug.utils import secure_filename
from datetime import datetime
import traceback
import logging
import sys
from statsmodels.tsa.arima.model import ARIMA
from sklearn.linear_model import LinearRegression
import xgboost as xgb

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

ALLOWED_EXTENSIONS = {'csv'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file part'}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No selected file'}), 400

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            return jsonify({'message': 'File uploaded successfully', 'filename': filename})

        return jsonify({'error': 'Invalid file type'}), 400
    except Exception as e:
        return jsonify({'error': f'Upload error: {str(e)}'}), 400

@app.route('/preview', methods=['POST'])
def preview_data():
    try:
        filename = request.json.get('filename')
        if not filename:
            return jsonify({'error': 'No filename provided'}), 400

        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        df = pd.read_csv(filepath)

        preview = df.head().to_dict('records')
        columns = df.columns.tolist()
        return jsonify({'preview': preview, 'columns': columns, 'rows': len(df)})
    except Exception as e:
        return jsonify({'error': f'Preview error: {str(e)}'}), 400

@app.route('/predict', methods=['POST'])
def predict():
    try:
        logger.info("=== Predict endpoint called ===")
        filename = request.json.get('filename')
        years_to_predict = int(request.json.get('years', 1))
        model_type = request.json.get('model', 'xgboost').lower()
        
        logger.info(f"Filename: {filename}, Years: {years_to_predict}, Model: {model_type}")

        if not filename:
            return jsonify({'error': 'No filename provided'}), 400

        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        logger.info(f"Reading CSV from: {filepath}")
        df = pd.read_csv(filepath)
        logger.info(f"CSV loaded: {len(df)} rows, {len(df.columns)} columns")

        # Validate CSV
        if len(df.columns) != 2:
            return jsonify({'error': 'CSV must have exactly two columns: date and sales'}), 400

        df['date'] = pd.to_datetime(df.iloc[:, 0])
        df['sales'] = pd.to_numeric(df.iloc[:, 1])
        df = df.rename(columns={'date': 'ds', 'sales': 'y'})

        # Use the last date in the data instead of hardcoded date
        df['ds'] = pd.to_datetime(df['ds'])
        actual_end = df['ds'].max()
        actual_df = df.copy()

        train_df = actual_df.copy()
        forecast = None

        # Select model
        logger.info(f"Starting {model_type} model training...")
        if model_type == 'prophet':
            import logging as prophet_logging
            prophet_logging.getLogger('prophet').setLevel(prophet_logging.WARNING)
            model = Prophet()
            model.fit(train_df)
            logger.info("Prophet model fitted")
            future = model.make_future_dataframe(periods=years_to_predict * 12, freq='MS')
            forecast = model.predict(future)[['ds', 'yhat']]
            logger.info("Prophet forecast completed")

        elif model_type == 'arima':
            y_series = train_df['y']
            model = ARIMA(y_series, order=(5, 1, 0))
            model_fit = model.fit()
            forecast_steps = years_to_predict * 12
            forecast_index = pd.date_range(start=actual_end + pd.Timedelta(days=1),
                                           periods=forecast_steps, freq='MS')
            forecast_values = model_fit.forecast(steps=forecast_steps)
            forecast = pd.DataFrame({'ds': forecast_index, 'yhat': forecast_values})

        elif model_type == 'xgboost':
            values = train_df['y'].values
            window_size = 5
            
            # Validate we have enough data
            if len(values) < window_size + 1:
                return jsonify({'error': f'XGBoost requires at least {window_size + 1} data points. Your data has {len(values)} points.'}), 400
            
            X, y_true = [], []
            for i in range(len(values) - window_size):
                X.append(values[i:i+window_size])
                y_true.append(values[i+window_size])
            X, y_true = np.array(X), np.array(y_true)

            model = xgb.XGBRegressor(objective='reg:squarederror', n_estimators=100)
            model.fit(X, y_true)

            preds = []
            last_window = values[-window_size:].copy()
            # Use monthly periods like other models for consistency
            forecast_periods = years_to_predict * 12
            for _ in range(forecast_periods):
                pred = model.predict(last_window.reshape(1, -1))[0]
                preds.append(pred)
                last_window = np.roll(last_window, -1)
                last_window[-1] = pred

            future_dates = pd.date_range(start=actual_end + pd.DateOffset(months=1),
                                         periods=forecast_periods, freq='MS')
            forecast = pd.DataFrame({'ds': future_dates, 'yhat': preds})

        elif model_type == 'linear':
            train_df['ds_ordinal'] = train_df['ds'].map(pd.Timestamp.toordinal)
            X = train_df[['ds_ordinal']]
            y = train_df['y']
            model = LinearRegression()
            model.fit(X, y)

            # Use monthly periods for consistency
            forecast_periods = years_to_predict * 12
            future_dates = pd.date_range(start=actual_end + pd.DateOffset(months=1),
                                         periods=forecast_periods, freq='MS')
            future_ordinals = future_dates.map(pd.Timestamp.toordinal).values.reshape(-1, 1)
            y_pred = model.predict(future_ordinals)
            forecast = pd.DataFrame({'ds': future_dates, 'yhat': y_pred})

        else:
            return jsonify({'error': f'Unknown model type: {model_type}'}), 400

        # --- Save unique forecast file ---
        logger.info("Saving forecast results...")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        forecast_filename = f"forecast_{model_type}_{timestamp}.csv"
        forecast_path = os.path.join(app.config['UPLOAD_FOLDER'], forecast_filename)

        forecast_to_save = forecast.rename(columns={'ds': 'date', 'yhat': 'predicted_sales'})
        forecast_to_save[['date', 'predicted_sales']].to_csv(forecast_path, index=False)
        logger.info(f"Forecast saved to: {forecast_filename}")

        # --- Create plot ---
        logger.info("Creating plot...")
        import plotly.graph_objs as go
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=actual_df['ds'], y=actual_df['y'], mode='lines+markers', name='Actual Sales'))
        fig.add_trace(go.Scatter(x=forecast['ds'], y=forecast['yhat'], mode='lines+markers', name='Predicted Sales'))
        plot_json = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)

        plot_filename = f"plot_{timestamp}.json"
        plot_path = os.path.join(app.config['UPLOAD_FOLDER'], plot_filename)
        with open(plot_path, 'w') as f:
            f.write(plot_json)
        logger.info(f"Plot saved to: {plot_filename}")

        # Return JSON with the URL instead of redirect for AJAX compatibility
        results_url = url_for('results', plot=plot_filename, forecast_file=forecast_filename)
        logger.info(f"Returning success with URL: {results_url}")
        return jsonify({'success': True, 'redirect_url': results_url})

    except Exception as e:
        error_details = traceback.format_exc()
        logger.error(f"=== PREDICTION ERROR ===")
        logger.error(f"Error message: {str(e)}")
        logger.error(f"Full traceback:\n{error_details}")
        return jsonify({'error': f'Prediction error: {str(e)}'}), 500

@app.route('/results')
def results():
    try:
        plot_filename = request.args.get('plot')
        forecast_filename = request.args.get('forecast_file')

        if not plot_filename or not forecast_filename:
            return redirect(url_for('index'))

        plot_path = os.path.join(app.config['UPLOAD_FOLDER'], plot_filename)
        with open(plot_path, 'r') as f:
            plot_json = f.read()

        return render_template('result.html', plot_data=plot_json, forecast_file=forecast_filename)

    except Exception as e:
        logger.error(f"Error in results page: {str(e)}")
        return redirect(url_for('index'))
@app.route('/download/<filename>')
def download_file(filename):
    try:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if not os.path.exists(file_path):
            return jsonify({'error': 'File not found'}), 404
        return send_file(file_path, as_attachment=True, download_name=filename)
    except Exception as e:
        return jsonify({'error': f'Download error: {str(e)}'}), 400

if __name__ == '__main__':
    app.run(debug=True)
