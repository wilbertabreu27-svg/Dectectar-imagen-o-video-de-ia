import os
import cv2
import numpy as np
from flask import Flask, request, render_template_string, jsonify
from PIL import Image, ExifTags
import threading
import time
import traceback

# Reduce parallelism inside numeric libraries to lower memory use
os.environ.setdefault('OMP_NUM_THREADS', '1')
os.environ.setdefault('MKL_NUM_THREADS', '1')

# Heavy ML deps (torch / transformers) are loaded lazily inside get_model()

app = Flask(__name__)

MODEL_NAME = "Organika/sdxl-detector"
# Globals populated on first use
model = None
feature_extractor = None
_model_lock = threading.Lock()
DEBUG_SHOW_STACK = os.environ.get('DEBUG_SHOW_STACK', 'false').lower() == 'true'
PREFILTER_THRESHOLD = 20.0  # reducir umbral para más sensibilidad


def get_model():
    """Carga el modelo y el extractor de forma perezosa y segura en multi-hilo.
    Usa low_cpu_mem_usage si está disponible para reducir picos de memoria.
    """
    global model, feature_extractor
    if model is not None and feature_extractor is not None:
        return model, feature_extractor

    with _model_lock:
        if model is not None and feature_extractor is not None:
            return model, feature_extractor

        try:
            import torch
            from transformers import AutoModelForImageClassification, AutoFeatureExtractor
        except Exception as e:
            raise RuntimeError(f"No se han podido cargar dependencias ML: {e}")

        device = "cuda" if torch.cuda.is_available() else "cpu"
        # Intentar reducir el uso de memoria durante la deserialización
        feature_extractor = AutoFeatureExtractor.from_pretrained(MODEL_NAME)
        # low_cpu_mem_usage requiere accelerate; si falla, reintentar sin ese argumento
        try:
            model = AutoModelForImageClassification.from_pretrained(MODEL_NAME, low_cpu_mem_usage=True)
        except Exception as e:
            print("Advertencia: no se pudo usar low_cpu_mem_usage (Accelerate no instalado?) -> fallback sin low_cpu_mem_usage:", str(e))
            try:
                model = AutoModelForImageClassification.from_pretrained(MODEL_NAME)
            except Exception as e2:
                raise RuntimeError(f"No se pudo cargar el modelo: {e2}")

        model.to(device)
        model.eval()
        return model, feature_extractor

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
            <label style="display:block;margin:10px 0;color:#cbd5e1;"><input type="checkbox" name="force_deep"> Forzar análisis profundo</label>
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
    # Cargar modelo/extractor perezosamente
    model, feature_extractor = get_model()
    try:
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        import warnings
        warnings.warn("Torch no disponible; forzando CPU")
        device = "cpu"

    inputs = feature_extractor(images=patch_img, return_tensors="pt")
    # BatchEncoding soporta .to, pero hacer fallback si no
    try:
        inputs = inputs.to(device)
    except Exception:
        for k, v in list(inputs.items()):
            if hasattr(v, 'to'):
                inputs[k] = v.to(device)

    with torch.no_grad():
        outputs = model(**inputs)
        probs = torch.nn.functional.softmax(outputs.logits, dim=-1)

    # Índice 1 representa contenido sintético/modificado según el modelo
    score = probs[0][1].item() * 100 if probs.shape[1] > 1 else probs[0][0].item() * 100
    return score

def forensic_grid_analysis(image_or_path, patch_size=256, stride=128):
    """Analiza una imagen (ruta o PIL.Image) por parches y devuelve la máxima puntuación.
    Esta función llama a analyze_patch que cargará el modelo si es necesario.
    """
    if isinstance(image_or_path, str):
        img = Image.open(image_or_path).convert("RGB")
    else:
        img = image_or_path.convert("RGB")

    width, height = img.size
    scores = []

    # Si la imagen es muy pequeña, se analiza completa
    if width < patch_size or height < patch_size:
        return analyze_patch(img)

    # Estrategia de parches deslizantes para detectar objetos agregados o recortes locales
    # Limitar el número máximo de parches para evitar sobrecarga en entornos con memoria limitada
    max_patches = 128
    patch_count = 0
    for y in range(0, height - patch_size + 1, stride):
        for x in range(0, width - patch_size + 1, stride):
            box = (x, y, x + patch_size, y + patch_size)
            patch = img.crop(box)
            score = analyze_patch(patch)
            scores.append(score)
            patch_count += 1
            if patch_count >= max_patches:
                break
        if patch_count >= max_patches:
            break

    # Incluir análisis global (si queda presupuesto)
    try:
        full_score = analyze_patch(img)
        scores.append(full_score)
    except Exception:
        pass

    max_score = max(scores) if scores else 0.0
    return max_score

def analyze_video_frames(video_path, max_frames=20):
    # Prefiltro ligero: muestrear fotogramas y buscar anomalías simples
    suspicious, details_score, sample_scores = prefilter_video(video_path, samples=min(6, max_frames))
    if not suspicious:
        # No hay indicios en el muestreo: devolver un score ligero basado en el prefiltro
        avg = float(np.mean(sample_scores)) if sample_scores else 0.0
        return avg, 0

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
        
        # Análisis forense profundo solo cuando el prefiltro muestra sospecha
        cv_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(cv_rgb)
        try:
            score = forensic_grid_analysis(pil_img)
        except Exception:
            score = 50.0
        frame_scores.append(score)
        
        frame_idx += step
        count += 1
        
    cap.release()
    max_v_score = max(frame_scores) if frame_scores else 0.0
    return max_v_score, temporal_anomalies


def prefilter_image(image_input):
    """Heurísticos ligeros para detectar manipulación en una imagen o PIL.Image.
    Devuelve (suspicious: bool, score: float, details: str).
    """
    # Acepta ruta o PIL.Image
    if isinstance(image_input, str):
        try:
            img = Image.open(image_input)
            path = image_input
        except Exception:
            return True, 75.0, "No se pudo abrir imagen"
    else:
        img = image_input
        path = None

    try:
        gray = np.array(img.convert('L'))
    except Exception:
        return True, 80.0, "Formato de imagen no válido"

    # Blur detection (varianza del Laplaciano)
    lap = cv2.Laplacian(gray, cv2.CV_64F)
    lap_var = float(lap.var())

    # Edge density
    edges = cv2.Canny(gray, 100, 200)
    edge_density = float(np.count_nonzero(edges)) / (gray.shape[0] * gray.shape[1])

    # Tamaño de archivo relativo -> posible recompresión
    file_size_kb = None
    if path and os.path.exists(path):
        try:
            file_size_kb = os.path.getsize(path) / 1024.0
        except Exception:
            file_size_kb = None

    # Regla heurística combinada
    score = 0.0
    # baja varianza laplaciana -> borrosa -> manipulación posible
    if lap_var < 50:
        score += 30
    # densidad de bordes muy baja o muy alta puede indicar recortes/pegados
    if edge_density < 0.01 or edge_density > 0.18:
        score += 30
    # muy pequeño tamaño en KB para resolución -> recompress
    if file_size_kb is not None:
        px = gray.shape[0] * gray.shape[1]
        ratio = file_size_kb / max(1, px/1000)
        if ratio < 0.5:
            score += 20

    # Error Level Analysis (ELA) ligero: re-guardar JPEG y comparar
    try:
        from io import BytesIO
        buf = BytesIO()
        # Re-guardar con calidad 95 y medir la diferencia media
        img.convert('RGB').save(buf, format='JPEG', quality=95)
        buf.seek(0)
        reimg = Image.open(buf)
        ela = np.abs(np.array(img.convert('RGB'), dtype=np.int16) - np.array(reimg.convert('RGB'), dtype=np.int16))
        ela_mean = float(np.mean(ela))
        # ELA mean alto indica posibles ediciones locales
        if ela_mean > 10:
            score += min(30, (ela_mean - 10))
    except Exception:
        ela_mean = 0.0

    # Detección de anomalías en bordes/cortes: comparar borde exterior con región interior
    try:
        h, w = gray.shape
        bw = max(4, int(min(w, h) * 0.05))
        outer_top = gray[0:bw, :]
        inner_top = gray[bw:bw*2, :]
        top_diff = float(np.mean(np.abs(outer_top.astype(int) - inner_top.astype(int))))

        outer_left = gray[:, 0:bw]
        inner_left = gray[:, bw:bw*2]
        left_diff = float(np.mean(np.abs(outer_left.astype(int) - inner_left.astype(int))))

        border_score = (top_diff + left_diff) / 2.0
        if border_score > 8:
            score += 25
    except Exception:
        border_score = 0.0

    # Umbral configurable
    suspicious = score >= PREFILTER_THRESHOLD
    details = f"lap_var={lap_var:.1f}, edge_density={edge_density:.3f}, ela_mean={ela_mean:.1f}, border_score={border_score:.1f}, score={score:.1f}"
    return suspicious, float(score), details


def prefilter_video(video_path, samples=6):
    """Muestrea frames periódicos y aplica prefilter_image. Devuelve (suspicious, avg_score, scores_list).
    """
    cap = cv2.VideoCapture(video_path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total <= 0:
        total = 1
    step = max(1, total // samples)
    scores = []
    suspicious_count = 0
    idx = 0
    for i in range(samples):
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = cap.read()
        if not ret:
            break
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        pil = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        sus, sc, det = prefilter_image(pil)
        scores.append(sc)
        if sus:
            suspicious_count += 1
        idx += step
    cap.release()
    avg = float(np.mean(scores)) if scores else 0.0
    # Si más de la mitad de muestras son sospechosas, marcar el video
    suspicious = suspicious_count >= max(1, samples // 2)
    return suspicious, avg, scores

@app.route('/', methods=['GET', 'POST'])
def index():
    result = None
    if request.method == 'POST':
        file = request.files.get('file')
        force_deep = True if request.form.get('force_deep') == 'on' else False
        filepath = None
        try:
            if not file:
                raise ValueError('No se ha recibido el archivo')

            filepath = os.path.join("uploads", file.filename)
            os.makedirs("uploads", exist_ok=True)
            file.save(filepath)

            ext = file.filename.split('.')[-1].lower()
            if ext in ['mp4', 'avi', 'mov', 'mkv']:
                max_score, anomalies = analyze_video_frames(filepath)
                file_type = "VIDEO (CCTV)"
            else:
                # Prefiltro ligero en imagenes
                suspicious, score, details = prefilter_image(filepath)
                # Forzar análisis profundo desde la UI
                if force_deep or suspicious:
                    max_score = forensic_grid_analysis(filepath)
                else:
                    # No sospecha en prefiltro: devolver puntuación ligera
                    max_score = score
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
        except Exception as e:
            # Log server-side
            tb = traceback.format_exc()
            print("Error procesando archivo:", str(e))
            print(tb)
            # Prepare friendly result
            details_msg = str(e)
            if DEBUG_SHOW_STACK:
                details_msg = f"{details_msg}\n\n{tb}"
            result = {
                "verdict": "ERROR INTERNO DEL SERVIDOR",
                "type": "N/A",
                "max_score": 0.0,
                "temporal_anomalies": 0,
                "details": details_msg
            }
        finally:
            try:
                if filepath and os.path.exists(filepath):
                    os.remove(filepath)
            except Exception:
                pass
            
    return render_template_string(HTML_TEMPLATE, result=result)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)