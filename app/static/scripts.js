function uploadFile()
{
    document.getElementById('fileUpload').click();
}

async function handleFileSelect(event)
{
    const file = event.target.files[0];
    if (!file) 
    {
        return;
    }

    alert('Uploading file: ' + file.name);

    const formData = new FormData();
    formData.append('file', file);
    
    try
    {
        const response = await fetch('http://localhost:5000/api/upload', {
            method: 'POST',
            body: formData
        });

        if (!response.ok)
            throw new Error('HTTP Error: ' + response.status);

        const result = await response.json();
        console.log('Success: ', result);
        alert(`File processed: ${result.message}`);

        if (result.data)
            displayUploadData(result.data);
    }
    catch (error)
    {
        console.error('Error uploading file:', error);
        alert('Error uploading file: ' + error.message);
    }

    event.target.value = '';
}

function displayUploadData(data)
{
    const contentArea = document.getElementById('uploadDataDisplay');
    contentArea.innerHTML = `
        <div style="background: white; padding: 20px; border: 2px solid var(--msu-gold); margin: 20px; border-radius: 8px;">
            <h2>Uploaded Data Preview</h2>
            <pre>${JSON.stringify(data, null, 2)}</pre>
        </div>
    `;
}