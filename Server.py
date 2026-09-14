import os
import cv2
import numpy as np
from flask import Flask, request, render_template_string, jsonify
import torch
from PIL import Image
from transformers import AutoModelForImageClassification, AutoFeatureExtractor

app = Flask(__name__)

MODEL_NAME = "Organika/sdxl-detector"
device = "cuda" if torch.cuda.is_available() else "cpu"

print(f"Cargando modelo forense en {device}...")
feature_extractor = AutoFeatureExtractor.from_pretrained(MODEL_NAME)
model = AutoModelForImageClassification.from_pretrained(MODEL_NAME).to(device)
model.eval()

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>Forensic AI Media Inspector</title>
    <style>
        body { font-family: Arial, sans-serif; background: #0f172a; color: #f8fafc; padding: 40px; }
        .container { max-width: 600px; margin: auto; background: #1e293b; padding: 30px; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.5); }
        input[type="file"] { margin: 20px 0; padding: 10px; background: #334155; border: none; color: #fff; width: 100%; border-radius: 6px; }
        button { background: #3b82f6; color: white; border: none; padding: 12px 20px; font-size: 16px; border-radius: 6px; cursor: pointer; width: 100%; }
        button:hover { background: #2563eb; }
        .result { margin-top: 20px; padding: 15px; background: #0f172a; border-radius: 6px; border-left: 5px solid #3b82f6; }
    </style>
</head>
<body>
    <div class="container">
        <h2>Auditoría Forense de Medios (CCTV / Imágenes)</h2>
        <form method="POST" enctype="multipart/form-data">
            <input type="file" name="file" accept="image/*,video/*" required>
            <button type="submit">Analizar Alteraciones o Recortes</button>
        </form>
        {% if result %}
        <div class="result">
            <h3>Veredicto: {{ result.verdict }}</h3>
            <p><b>Tipo de Archivo:</b> {{ result.type }}</p>
            <p><b>Puntuación de Anomalía Máxima:</b> {{ result.max_score }}%</p>
            <p><b>Anomalías Temporales / Cortes bruscos (CCTV):</b> {{ result.temporal_anomalies }}</p>
            <p><b>Detalles:</b> {{ result.details }}</p>
        </div>
        {% endif %}
    </div>
</body>
</html>
"""

def analyze_patch(patch_img):
    inputs = feature_extractor(images=patch_img, return_tensors="pt").to(device)
    with torch.no_grad():
        outputs = model(**inputs)
        probs = torch.nn.functional.softmax(outputs.logits, dim=-1)
    # Índice 1 representa contenido sintético/modificado según los pesos del modelo
    score = probs[0][1].item() * 100 if probs.shape[1] > 1 else probs[0][0].item() * 100
    return score

def forensic_grid_analysis(image_path, patch_size=256, stride=128):
    img = Image.open(image_path).convert("RGB")
    width, height = img.size
    
    scores = []
    # Si la imagen es muy pequeña, se analiza completa
    if width < patch_size or height < patch_size:
        return analyze_patch(img), 1
        
    # Estrategia de parches deslizantes para detectar objetos agregados o recortes locales
    for y in range(0, height - patch_size + 1, stride):
        for x in range(0, width - patch_size + 1, stride):
            box = (x, y, x + patch_size, y + patch_size)
            patch = img.crop(box)
            score = analyze_patch(patch)
            scores.append(score)
            
    # Incluir análisis global
    full_score = analyze_patch(img)
    scores.append(full_score)
    
    max_score = max(scores) if scores else full_score
    return max_score

def analyze_video_frames(video_path, max_frames=20):
    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_frames <= 0:
        total_frames = 1
        
    frame_scores = []
    prev_gray = None
    temporal_anomalies = 0
    
    step = max(1, total_frames // max_frames)
    frame_idx = 0
    count = 0
    
    while cap.isOpened() and count < max_frames:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if not ret:
            break
            
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # Detección de cortes artificiales / empalmes de video (CCTV tampering)
        if prev_gray is not None:
            diff = cv2.absdiff(prev_gray, gray)
            changed_pixels = np.count_nonzero(diff > 40)
            # Un cambio masivo instantáneo sin transición de flujo óptico denota corte/empalme de escena
            if changed_pixels > (gray.shape[0] * gray.shape[1] * 0.5):
                temporal_anomalies += 1
                
        prev_gray = gray
        
        # Análisis de IA por fotograma individual
        cv_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(cv_rgb)
        score = forensic_grid_analysis(pil_img) if hasattr(pil_img, 'size') else 50.0
        frame_scores.append(score)
        
        frame_idx += step
        count += 1
        
    cap.release()
    max_v_score = max(frame_scores) if frame_scores else 0.0
    return max_v_score, temporal_anomalies

@app.route('/', methods=['GET', 'POST'])
def index():
    result = None
    if request.method == 'POST':
        file = request.files['file']
        if file:
            filepath = os.path.join("uploads", file.filename)
            os.makedirs("uploads", exist_ok=True)
            file.save(filepath)
            
            ext = file.filename.split('.')[-1].lower()
            if ext in ['mp4', 'avi', 'mov', 'mkv']:
                max_score, anomalies = analyze_video_frames(filepath)
                file_type = "VIDEO (CCTV)"
            else:
                max_score = forensic_grid_analysis(filepath)
                anomalies = 0
                file_type = "IMAGEN"
                
            verdict = "ALTAMENTE SOSPECHOSO / ALTERADO" if max_score > 65 or anomalies > 0 else "PROBABLEMENTE AUTÉNTICO"
            
            result = {
                "verdict": verdict,
                "type": file_type,
                "max_score": round(max_score, 2),
                "temporal_anomalies": anomalies,
                "details": f"Análisis de parches y coherencia aplicado. Puntuación de riesgo de manipulación: {round(max_score, 2)}%"
            }
            os.remove(filepath)
            
    return render_template_string(HTML_TEMPLATE, result=result)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)