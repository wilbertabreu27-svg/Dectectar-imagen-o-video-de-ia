import os
import cv2
import torch
import torch.nn.functional as F
from flask import Flask, request, jsonify, render_template
from PIL import Image
from transformers import AutoModelForImageClassification, AutoImageProcessor

app = Flask(__name__, template_folder='templates', static_folder='static')
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Cargar modelo y procesador de Hugging Face
MODEL_NAME = "umm-maybe/AI-image-detector"
print("Cargando modelo de IA...")
processor = AutoImageProcessor.from_pretrained(MODEL_NAME)
model = AutoModelForImageClassification.from_pretrained(MODEL_NAME)
model.eval()
print("Modelo cargado exitosamente.")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/analizar-imagen', methods=['POST'])
def analizar_imagen():
    if 'file' not in request.files:
        return jsonify({"error": "No se envió ningún archivo"}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "Nombre de archivo vacío"}), 400
        
    try:
        image = Image.open(file.stream).convert("RGB")
        inputs = processor(images=image, return_tensors="pt")
        
        with torch.no_grad():
            outputs = model(**inputs)
            logits = outputs.logits
            probs = F.softmax(logits, dim=-1)
            
        predicted_class_idx = logits.argmax(-1).item()
        confidence = probs[0][predicted_class_idx].item() * 100
        etiquetas = model.config.id2label
        veredicto = etiquetas[predicted_class_idx]
        
        return jsonify({
            "tipo": "imagen",
            "veredicto": veredicto.upper(),
            "confianza": round(confidence, 2)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/analizar-video', methods=['POST'])
def analizar_video():
    if 'file' not in request.files:
        return jsonify({"error": "No se envió ningún archivo"}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "Nombre de archivo vacío"}), 400
        
    path = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(path)
    
    try:
        cap = cv2.VideoCapture(path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        frame_interval = int(fps) # Analizar 1 fotograma por segundo
        
        confianzas = []
        fake_counts = 0
        count = 0
        
        etiquetas = model.config.id2label
        
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            if count % frame_interval == 0:
                # Convertir BGR de OpenCV a RGB para PIL
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                image = Image.fromarray(rgb_frame)
                
                inputs = processor(images=image, return_tensors="pt")
                with torch.no_grad():
                    outputs = model(**inputs)
                    logits = outputs.logits
                    probs = F.softmax(logits, dim=-1)
                    
                idx = logits.argmax(-1).item()
                conf = probs[0][idx].item() * 100
                veredicto_frame = etiquetas[idx].lower()
                
                confianzas.append(conf)
                if "fake" in veredicto_frame or "artificial" in veredicto_frame:
                    fake_counts += 1
            count += 1
            
        cap.release()
        os.remove(path)
        
        if not confianzas:
            return jsonify({"error": "No se pudieron procesar fotogramas del video"}), 400
            
        promedio_conf = sum(confianzas) / len(confianzas)
        es_fake = fake_counts > (len(confianzas) / 2)
        
        return jsonify({
            "tipo": "video",
            "veredicto": "FAKE (VIDEO ARTIFICIAL)" if es_fake else "REAL",
            "confianza": round(promedio_conf, 2),
            "detalles": f"Se analizaron {len(confianzas)} fotogramas clave."
        })
    except Exception as e:
        if os.path.exists(path):
            os.remove(path)
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)