import os
import io
import cv2
import base64
import hashlib
import gc
import numpy as np
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from PIL import Image, ImageChops, ImageEnhance
import torch

# Optimizaciones extremas de RAM para entornos de bajos recursos (Render Free Tier)
torch.set_num_threads(1)
torch.set_grad_enabled(False)
device = torch.device("cpu")

app = Flask(__name__)
CORS(app)
print("Iniciando Motor Forense Optimizado (Modo Ahorro de RAM)...")

detector_sintetico = None

def obtener_detector():
    global detector_sintetico
    if detector_sintetico is None:
        try:
            from transformers import pipeline
            print("Cargando modelo de clasificación en CPU...")
            detector_sintetico = pipeline(
                "image-classification", 
                model="umm-maybe/AI-image-detector",
                device=-1
            )
            print("-> Red Neuronal Forense activa.")
        except Exception as e:
            print(f"Advertencia al cargar modelo de IA: {e}")
            detector_sintetico = False
    return detector_sintetico if detector_sintetico is not False else None

def generar_hash_md5(imagen_pil):
    buffer = io.BytesIO()
    imagen_pil.save(buffer, format='JPEG')
    return hashlib.md5(buffer.getvalue()).hexdigest()

def analizar_metadatos_y_camara(pil_img):
    exif = pil_img._getexif() if hasattr(pil_img, '_getexif') else None
    if not exif:
        return True, "Ausencia total de metadatos EXIF de hardware de cámara (Típico de IA y descargas web)."
    tiene_camara = 271 in exif or 272 in exif
    if not tiene_camara:
        return True, "Estructura EXIF presente pero sin marca/modelo de sensor de cámara física."
    return False, "Metadatos coherentes con un sensor de cámara física."

def analizar_ruido_sensor_prnu(imagen_cv):
    gray = cv2.cvtColor(imagen_cv, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    ruido = cv2.absdiff(gray, blur)
    desviacion_ruido = float(np.std(ruido))
    media_ruido = float(np.mean(ruido))
    es_grano_sintetico = (media_ruido > 0) and (desviacion_ruido / media_ruido < 1.15)
    return round(desviacion_ruido, 2), es_grano_sintetico

def analizar_espectro_fft(imagen_cv):
    gray = cv2.cvtColor(imagen_cv, cv2.COLOR_BGR2GRAY)
    f = np.fft.fft2(gray)
    fshift = np.fft.fftshift(f)
    magnitude_spectrum = 20 * np.log(np.abs(fshift) + 1e-8)
    h, w = gray.shape
    cy, cx = h // 2, w // 2
    r = 30
    magnitude_spectrum[cy-r:cy+r, cx-r:cx+r] = 0
    pico = float(np.max(magnitude_spectrum))
    promedio = float(np.mean(magnitude_spectrum))
    return round(pico / (promedio + 1e-5), 2)

def detectar_recortes_y_montajes(imagen_cv):
    gray = cv2.cvtColor(imagen_cv, cv2.COLOR_BGR2GRAY)
    sobelx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    sobely = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    magnitud = cv2.magnitude(sobelx, sobely)
    promedio = float(np.mean(magnitud))
    desviacion = float(np.std(magnitud))
    return round(desviacion / (promedio + 1e-5), 2)

def detectar_filtros_histograma(imagen_cv):
    hsv = cv2.cvtColor(imagen_cv, cv2.COLOR_BGR2HSV)
    hist_sat = cv2.calcHist([hsv], [1], None, [256], [0, 256])
    valles_vacios = np.sum(hist_sat == 0)
    return round((valles_vacios / 256.0) * 100, 2)

def generar_mapa_ela(imagen_pil, calidad=90):
    buffer = io.BytesIO()
    img_rgb = imagen_pil.convert('RGB')
    img_rgb.save(buffer, 'JPEG', quality=calidad)
    buffer.seek(0)
    img_recomprimida = Image.open(buffer)
    diferencia = ImageChops.difference(img_rgb, img_recomprimida)
    extrema = diferencia.getextrema()
    max_diff = max([ex[1] for ex in extrema]) or 1
    escala = 255.0 / max_diff
    diferencia_amplificada = ImageEnhance.Brightness(diferencia).enhance(escala)
    stat_diff = np.array(diferencia)
    promedio_diferencia = float(np.mean(stat_diff))
    output_buffer = io.BytesIO()
    diferencia_amplificada.save(output_buffer, format='JPEG')
    ela_base64 = base64.b64encode(output_buffer.getvalue()).decode('utf-8')
    return ela_base64, round(promedio_diferencia, 2)

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/analizar_master', methods=['POST'])
def analizar_master():
    if 'file' not in request.files:
        return jsonify({'error': 'No se subió ningún archivo.'}), 400

    file = request.files['file']

    try:
        img_bytes = file.read()
        nparr = np.frombuffer(img_bytes, np.uint8)
        img_cv = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        pil_img = Image.open(io.BytesIO(img_bytes)).convert('RGB')
        
        prob_ia = 0.0
        detector = obtener_detector()
        if detector:
            res = detector(pil_img)
            for item in res:
                if any(k in item['label'].lower() for k in ['fake', 'ai', 'synthetic', 'artificial']):
                    prob_ia = round(item['score'] * 100, 2)
                    break

        sin_exif_camara, msj_exif = analizar_metadatos_y_camara(pil_img)
        nivel_ruido, es_grano_sintetico = analizar_ruido_sensor_prnu(img_cv)
        ratio_fft = analizar_espectro_fft(img_cv)
        anomalia_recorte = detectar_recortes_y_montajes(img_cv)
        nivel_filtro = detectar_filtros_histograma(img_cv)
        ela_b64, dif_ela = generar_mapa_ela(pil_img)

        es_sintetica_ia = (
            (prob_ia > 10.0) or
            (sin_exif_camara and es_grano_sintetico) or
            (sin_exif_camara and (nivel_ruido < 3.0 or ratio_fft > 1.5))
        )

        es_recorte = anomalia_recorte > 3.8 or dif_ela > 14.0
        tiene_filtro = nivel_filtro > 60.0

        detalles = []
        hash_img = generar_hash_md5(pil_img)
        detalles.append(f"Hash MD5 de archivo: {hash_img[:12]}...")
        detalles.append(f"Análisis EXIF: {msj_exif}")

        if es_grano_sintetico:
            detalles.append(f"Nivel de ruido PRNU: {nivel_ruido} pts (DETECTADO GRANO SINTÉTICO).")
        else:
            detalles.append(f"Nivel de ruido PRNU: {nivel_ruido} pts.")

        detalles.append(f"Espectro FFT: Ratio {ratio_fft}.")

        if es_sintetica_ia:
            diagnostico = "IMAGEN GENERADA POR INTELIGENCIA ARTIFICIAL (Sintética Detectada)"
            riesgo = "Alto"
            detalles.append("Bloqueo de seguridad: Ausencia de sensor físico y presencia de artefactos latentes.")
        elif es_recorte:
            diagnostico = "IMAGEN MANIPULADA / RECORTE O MONTAJE DETECTADO"
            riesgo = "Medio"
            detalles.append("Inconsistencia en bordes Sobel y compresión ELA.")
        elif tiene_filtro:
            diagnostico = "FOTO REAL CON FILTROS DE REDES SOCIALES"
            riesgo = "Bajo"
            detalles.append("Alteración severa en el histograma de saturación/color.")
        else:
            diagnostico = "FOTO REAL TOMADA CON CÁMARA FÍSICA"
            riesgo = "Bajo"

        del img_bytes
        del nparr
        del img_cv
        del pil_img
        gc.collect()

        return jsonify({
            'tipo': 'Imagen',
            'diagnostico': diagnostico,
            'nivel_riesgo': riesgo,
            'probabilidad_ia': f"{prob_ia}%",
            'indice_recorte': f"{anomalia_recorte} pts",
            'nivel_filtro': f"{nivel_filtro}%",
            'investigacion': detalles,
            'mapa_ela': f"data:image/jpeg;base64,{ela_b64}"
        })

    except Exception as e:
        gc.collect()
        return jsonify({'error': f"Error en la inspección forense: {str(e)}"}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)