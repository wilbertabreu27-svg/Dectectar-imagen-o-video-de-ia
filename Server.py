import os
import cv2
import numpy as np
from flask import Flask, request, jsonify, render_template

app = Flask(__name__, template_folder='templates', static_folder='static')
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def evaluar_espectro_fft(imagen_cv2):
    # Convertir a escala de grises si no lo está
    if len(imagen_cv2.shape) == 3:
        gray = cv2.cvtColor(imagen_cv2, cv2.COLOR_BGR2GRAY)
    else:
        gray = imagen_cv2
        
    # Aplicar Transformada de Fourier bidimensional (FFT)
    f = np.fft.fft2(gray)
    fshift = np.fft.fftshift(f)
    magnitude_spectrum = 20 * np.log(np.abs(fshift) + 1)
    
    # La desviación estándar del espectro funciona como indicador de patrones artificiales
    score = float(np.std(magnitude_spectrum))
    return score

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/analizar', methods=['POST'])
def api_analizar():
    if 'file' not in request.files:
        return jsonify({"error": "No se envió ningún archivo"}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "Nombre de archivo vacío"}), 400
        
    path = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(path)
    
    try:
        # Detectar si es un video o una imagen por su extensión
        ext = file.filename.lower().split('.')[-1]
        extensiones_video = ['mp4', 'mov', 'avi', 'mkv', 'webm']
        
        if ext in extensiones_video:
            cap = cv2.VideoCapture(path)
            fps = cap.get(cv2.CAP_PROP_FPS) or 30
            frame_interval = int(fps) # Analizar 1 fotograma por segundo
            
            scores = []
            count = 0
            while cap.isOpened():
                ret, frame = cap.read()
                if not ret: 
                    break
                if count % frame_interval == 0:
                    score_frame = evaluar_espectro_fft(frame)
                    scores.append(score_frame)
                count += 1
            cap.release()
            
            promedio_score = sum(scores) / len(scores) if scores else 0
            # Umbral referencial de análisis agnóstico
            es_ia = promedio_score > 120.0
            
            os.remove(path)
            return jsonify({
                "tipo": "video",
                "score": round(promedio_score, 2),
                "veredicto": "VIDEO PROBABLEMENTE FALSO (ANOMALÍAS DE IA)" if es_ia else "VIDEO PROBABLEMENTE REAL",
                "detalles": f"Se analizaron {len(scores)} fotogramas clave."
            })
            
        else:
            # Procesamiento de Imagen
            img = cv2.imread(path)
            if img is None:
                os.remove(path)
                return jsonify({"error": "No se pudo leer la imagen"}), 400
                
            score = evaluar_espectro_fft(img)
            es_ia = score > 120.0
            
            os.remove(path)
            return jsonify({
                "tipo": "imagen",
                "score": round(score, 2),
                "veredicto": "IMAGEN PROBABLEMENTE FALSA (PATRÓN SINTÉTICO)" if es_ia else "IMAGEN PROBABLEMENTE REAL",
                "detalles": f"Puntuación de densidad espectral: {round(score, 2)}"
            })
            
    except Exception as e:
        if os.path.exists(path): 
            os.remove(path)
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)