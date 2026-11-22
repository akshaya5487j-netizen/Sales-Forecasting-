let uploadedFilename = '';

document.getElementById('upload-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const fileInput = document.getElementById('file');
    const file = fileInput.files[0];
    const errorAlert = document.getElementById('error-alert');
    
    if (!file) {
        showError('Please select a file');
        return;
    }
    
    const formData = new FormData();
    formData.append('file', file);
    
    showLoading(true);
    
    try {
        const response = await fetch('/upload', {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.error || 'Upload failed');
        }
        
        uploadedFilename = data.filename;
        await previewData(uploadedFilename);
        
    } catch (error) {
        showError(error.message);
    } finally {
        showLoading(false);
    }
});

async function previewData(filename) {
    try {
        const response = await fetch('/preview', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ filename })
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.error || 'Preview failed');
        }
        
        displayPreview(data);
        
    } catch (error) {
        showError(error.message);
    }
}

function displayPreview(data) {
    const previewCard = document.getElementById('preview-card');
    const previewContent = document.getElementById('preview-content');
    
    let html = `<p><strong>Total Rows:</strong> ${data.rows}</p>`;
    html += `<p><strong>Columns:</strong> ${data.columns.join(', ')}</p>`;
    html += '<h6 class="mt-3">First 5 Rows:</h6>';
    html += '<div class="table-responsive"><table class="table table-sm table-striped">';
    html += '<thead><tr>';
    
    data.columns.forEach(col => {
        html += `<th>${col}</th>`;
    });
    html += '</tr></thead><tbody>';
    
    data.preview.forEach(row => {
        html += '<tr>';
        data.columns.forEach(col => {
            html += `<td>${row[col]}</td>`;
        });
        html += '</tr>';
    });
    
    html += '</tbody></table></div>';
    
    previewContent.innerHTML = html;
    previewCard.style.display = 'block';
}

document.getElementById('predict-btn').addEventListener('click', async () => {
    const years = document.getElementById('years').value;
    const model = document.getElementById('model').value;
    
    console.log('Predict button clicked');
    console.log('Uploaded filename:', uploadedFilename);
    console.log('Years:', years, 'Model:', model);
    
    if (!uploadedFilename) {
        showError('Please upload a file first');
        return;
    }
    
    showLoading(true);
    
    try {
        console.log('Sending predict request...');
        const response = await fetch('/predict', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                filename: uploadedFilename,
                years: parseInt(years),
                model: model
            })
        });
        
        console.log('Response status:', response.status);
        const data = await response.json();
        console.log('Response data:', data);
        
        if (!response.ok) {
            throw new Error(data.error || 'Prediction failed');
        }
        
        // Redirect to results page
        if (data.success && data.redirect_url) {
            console.log('Redirecting to:', data.redirect_url);
            window.location.href = data.redirect_url;
        } else {
            showError('Unexpected response from server');
            showLoading(false);
        }
        
    } catch (error) {
        console.error('Prediction error:', error);
        showError(error.message);
        showLoading(false);
    }
});

function showError(message) {
    const errorAlert = document.getElementById('error-alert');
    errorAlert.textContent = message;
    errorAlert.style.display = 'block';
    
    setTimeout(() => {
        errorAlert.style.display = 'none';
    }, 5000);
}

function showLoading(show) {
    const loading = document.getElementById('loading');
    loading.style.display = show ? 'block' : 'none';
}
