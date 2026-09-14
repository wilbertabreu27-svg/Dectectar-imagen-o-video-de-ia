import os
import cv2
import numpy as np
from flask import Flask, request, render_template_string, jsonify
from PIL import Image, ExifTags
import threading
import time
import traceback
import requests
import base64
import hashlib
import json
from io import BytesIO
from PIL import ImageDraw, ImageFilter

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
DEEP_REQUIRED_MB = int(os.environ.get('DEEP_REQUIRED_MB', '1000'))  # mínimo MB para permitir modelo


def detect_memory_limit_bytes():
    """Detecta límite de memoria del contenedor (cgroup v1/v2) o total del sistema.
    Devuelve bytes o None si no se puede determinar.
    """
    try:
        # cgroup v1
        path1 = '/sys/fs/cgroup/memory/memory.limit_in_bytes'
        if os.path.exists(path1):
            with open(path1, 'r') as f:
                v = int(f.read().strip())
                return v
        # cgroup v2
        path2 = '/sys/fs/cgroup/memory.max'
        if os.path.exists(path2):
            with open(path2, 'r') as f:
                txt = f.read().strip()
                if txt.isdigit():
                    return int(txt)
                # 'max' means no limit
        # fallback a /proc/meminfo
        if os.path.exists('/proc/meminfo'):
            with open('/proc/meminfo', 'r') as f:
                for line in f:
                    if line.startswith('MemTotal:'):
                        parts = line.split()
                        kb = int(parts[1])
                        return kb * 1024
    except Exception:
        return None
    return None


MEM_LIMIT_BYTES = detect_memory_limit_bytes()
if MEM_LIMIT_BYTES is None:
    # desconocido: conservador, desactivar modo profundo
    DEEP_AVAILABLE = False
else:
    DEEP_AVAILABLE = (MEM_LIMIT_BYTES >= DEEP_REQUIRED_MB * 1024 * 1024)
HF_API_TOKEN = os.environ.get('HF_API_TOKEN')
USE_REMOTE_WHEN_AVAILABLE = os.environ.get('USE_REMOTE_WHEN_AVAILABLE', 'true').lower() in ('1','true','yes')
HF_CACHE_DIR = os.environ.get('HF_CACHE_DIR', 'hf_cache')
os.makedirs(HF_CACHE_DIR, exist_ok=True)


def get_model():
    """Carga el modelo y el extractor de forma perezosa y segura en multi-hilo.
    Usa low_cpu_mem_usage si está disponible para reducir picos de memoria.
    """
    global model, feature_extractor
    if model is not None and feature_extractor is not None:
        return model, feature_extractor

    if not DEEP_AVAILABLE:
        raise RuntimeError(f"Análisis profundo deshabilitado: memoria del contenedor < {DEEP_REQUIRED_MB} MB")

    with _model_lock:
        if model is not None and feature_extractor is not None:
            return model, feature_extractor

        try:
            import torch
            from transformers import AutoModelForImageClassification, AutoFeatureExtractor
        except Exception as e:
            raise RuntimeError(f"No se han podido cargar dependencias ML: {e}. Si no puedes instalarlas en este contenedor, define HF_API_TOKEN para usar la API de Hugging Face como fallback.")

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
        {% if not deep_available %}
        <div style="margin-top:10px;padding:10px;background:#7f1d1d;color:#fee2e2;border-radius:6px;">Análisis profundo DESACTIVADO por memoria limitada del contenedor. En Render gratuito (512MB) no se puede cargar modelos pesados. Usa "Forzar análisis profundo" solo si sabes que la instancia tiene más RAM.</div>
        {% endif %}
        {% if result %}
        <div class="result">
            <h3>Veredicto: {{ result.verdict }}</h3>
            <p><b>Tipo de Archivo:</b> {{ result.type }}</p>
            <p><b>Puntuación de Anomalía Máxima:</b> {{ result.max_score }}%</p>
            <p><b>Anomalías Temporales / Cortes bruscos (CCTV):</b> {{ result.temporal_anomalies }}</p>
            <p><b>Detalles:</b> {{ result.details }}</p>
            {% if result.heatmap %}
            <p><b>Mapa de calor (heatmap):</b></p>
            <img src="{{ result.heatmap }}" alt="heatmap" style="max-width:100%;border-radius:6px;border:1px solid #334155;"/>
            {% endif %}
        </div>
        {% endif %}
    </div>
</body>
</html>
"""

def analyze_patch(patch_img):
    # Si se ha configurado, usar siempre la API remota (simula modelo pesado sin RAM local)
    if HF_API_TOKEN and USE_REMOTE_WHEN_AVAILABLE:
        try:
            score = remote_model_infer(patch_img)
            return score
        except Exception:
            # si la remota falla, continuar e intentar cargar modelo local
            pass

    # Cargar modelo/extractor perezosamente
    try:
        model, feature_extractor = get_model()
    except Exception as e:
        # Modelo pesado no disponible (memoria o dependencias)
        # Intentar usar la API de Hugging Face si hay token
        if HF_API_TOKEN:
            try:
                score = remote_model_infer(patch_img)
                if score is not None:
                    return score
            except Exception:
                pass

        # Devolver puntuación conservadora basada en heurísticos ligeros
        try:
            sus, score, details = prefilter_image(patch_img)
            return score
        except Exception:
            return 50.0
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

    # Si el contenedor no permite análisis profundo local pero disponemos de HF_API_TOKEN,
    # usar la API remota con la imagen completa (evita múltiples llamadas por parche).
    if not DEEP_AVAILABLE and HF_API_TOKEN:
        try:
            return remote_model_infer(img)
        except Exception:
            # continuar con análisis local heurístico
            pass

    # Si la imagen es muy pequeña, se analiza completa
    if width < patch_size or height < patch_size:
        return analyze_patch(img)

    # Estrategia en dos fases para minimizar memoria y llamadas remotas:
    # 1) Prefiltro ligero por parches (heurístico local) para encontrar regiones sospechosas.
    # 2) Aplicar análisis profundo SOLO a los N parches más sospechosos (local o remoto según disponibilidad).

    # Limitar número de parches analizados por heurístico para rendimiento
    max_sampled = 256
    candidates = []  # list of (heur_score, (x,y,box), patch_image)
    patch_count = 0
    for y in range(0, height - patch_size + 1, stride):
        for x in range(0, width - patch_size + 1, stride):
            box = (x, y, x + patch_size, y + patch_size)
            patch = img.crop(box)
            try:
                sus, hscore, _ = prefilter_image(patch)
            except Exception:
                hscore = 0.0
            candidates.append((hscore, box, patch))
            patch_count += 1
            if patch_count >= max_sampled:
                break
        if patch_count >= max_sampled:
            break

    if not candidates:
        # Fallback: analyze full image
        try:
            return analyze_patch(img)
        except Exception:
            return 0.0

    # Seleccionar top-K parches por heurística
    top_k = min(24, len(candidates))
    candidates.sort(key=lambda t: t[0], reverse=True)
    selected = candidates[:top_k]

    deep_scores = []
    # Ejecutar análisis profundo sobre los parches seleccionados
    for hscore, box, patch in selected:
        try:
            # analyze_patch maneja fallback remoto si el modelo local no está disponible
            ds = analyze_patch(patch)
        except Exception:
            # si falla, intentar inferencia remota directa
            try:
                ds = remote_model_infer(patch) if HF_API_TOKEN else hscore
            except Exception:
                ds = hscore
        deep_scores.append(ds)

    # También intentar analizar la imagen completa si al menos un parche presentó alta sospecha
    # Llamada remota completa si está disponible y/o si muchos parches son sospechosos
    try_full = False
    try:
        if HF_API_TOKEN and USE_REMOTE_WHEN_AVAILABLE:
            # llamar primero a la inferencia remota sobre la imagen completa
            full_remote = remote_model_infer(img)
            deep_scores.append(full_remote)
            try_full = True
        else:
            try_full = any(s >= 40 for s in deep_scores) or any(c[0] >= 40 for c in candidates)
            if try_full:
                try:
                    full = analyze_patch(img)
                    deep_scores.append(full)
                except Exception:
                    pass
    except Exception:
        # si la remota falla, seguir con lo que tengamos
        try_full = any(s >= 40 for s in deep_scores) or any(c[0] >= 40 for c in candidates)

    max_score = max(deep_scores) if deep_scores else 0.0

    # Generar heatmap simple basado en heur_score y deep_scores
    try:
        heat = Image.new('L', (width, height), color=0)
        draw = ImageDraw.Draw(heat)
        # map selected deep scores back to positions
        for idx, (hscore, box, patch) in enumerate(selected):
            x0, y0, x1, y1 = box
            ds = deep_scores[idx] if idx < len(deep_scores) else hscore
            val = int(max(0, min(255, (ds / 100.0) * 255)))
            draw.rectangle([x0, y0, x1, y1], fill=val)
        # blur for nicer visualization
        heat = heat.filter(ImageFilter.GaussianBlur(radius=patch_size//8))
        buf = BytesIO()
        heat.convert('RGB').save(buf, format='PNG')
        buf.seek(0)
        heat_b64 = base64.b64encode(buf.read()).decode('ascii')
        heatmap_data = f"data:image/png;base64,{heat_b64}"
    except Exception:
        heatmap_data = None

    # devolver máximo y heatmap
    return max_score, heatmap_data

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
            res = forensic_grid_analysis(pil_img)
            if isinstance(res, tuple):
                score = res[0]
            else:
                score = res
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


def remote_model_infer(pil_img, timeout=30):
    """Envía la imagen a la API de Inference de Hugging Face y devuelve una puntuación (0-100).
    Requiere HF_API_TOKEN en variables de entorno.
    """
    if not HF_API_TOKEN:
        raise RuntimeError('HF_API_TOKEN no configurado')

    url = f"https://api-inference.huggingface.co/models/{MODEL_NAME}"
    headers = {"Authorization": f"Bearer {HF_API_TOKEN}"}

    # Use a cache keyed by image bytes + model name
    buf = BytesIO()
    pil_img.save(buf, format='PNG')
    buf.seek(0)
    data = buf.read()

    # cache key
    h = hashlib.sha256()
    h.update(MODEL_NAME.encode('utf-8'))
    h.update(data)
    key = h.hexdigest()
    cache_file = os.path.join(HF_CACHE_DIR, key + '.json')
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as cf:
                cached = json.load(cf)
                return float(cached.get('score', 0.0))
        except Exception:
            pass

    r = requests.post(url, headers=headers, data=data, timeout=timeout)
    if r.status_code != 200:
        raise RuntimeError(f"HF API error: {r.status_code} {r.text}")

    try:
        resp = r.json()
    except Exception:
        raise RuntimeError('Respuesta no JSON de HF Inference')

    # Intentar interpretar la respuesta
    # Formato esperado: lista de {label, score}
    if isinstance(resp, list) and len(resp) > 0 and isinstance(resp[0], dict):
        # En muchos detectores: labels como 'REAL'/'FAKE' o 'SYNTHETIC'
        best = max(resp, key=lambda x: x.get('score', 0))
        best_label = str(best.get('label', '')).lower()
        best_score = float(best.get('score', 0.0))

        # Si encontramos etiqueta que sugiere manipulado/ai/fake, usar su score
        for item in resp:
            lab = str(item.get('label', '')).lower()
            if any(k in lab for k in ('synt', 'fake', 'ai', 'manip', 'alter')):
                return float(item.get('score', 0.0)) * 100.0

        # Si aparece 'real' o 'authentic', invertir
        for item in resp:
            lab = str(item.get('label', '')).lower()
            if any(k in lab for k in ('real', 'auth', 'genuine')):
                return (1.0 - float(item.get('score', 0.0))) * 100.0

        # Fallback: devolver mejor score *100
        score_out = best_score * 100.0
        # cache
        try:
            with open(cache_file, 'w', encoding='utf-8') as cf:
                json.dump({'score': score_out, 'resp': resp}, cf)
        except Exception:
            pass
        return score_out

    # Si la respuesta no es la esperada, intentar heurístico
    raise RuntimeError('Formato de respuesta HF inesperado')

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
                    res = forensic_grid_analysis(filepath)
                    if isinstance(res, tuple):
                        max_score, heatmap_data = res
                    else:
                        max_score = res
                        heatmap_data = None
                else:
                    # No sospecha en prefiltro: devolver puntuación ligera
                    max_score = score
                    heatmap_data = None
                anomalies = 0
                file_type = "IMAGEN"

            verdict = "ALTAMENTE SOSPECHOSO / ALTERADO" if max_score > 65 or anomalies > 0 else "PROBABLEMENTE AUTÉNTICO"

            result = {
                "verdict": verdict,
                "type": file_type,
                "max_score": round(max_score, 2),
                "temporal_anomalies": anomalies,
                "details": f"Análisis de parches y coherencia aplicado. Puntuación de riesgo de manipulación: {round(max_score, 2)}%",
                "heatmap": heatmap_data if 'heatmap_data' in locals() else None
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
            
    return render_template_string(HTML_TEMPLATE, result=result, deep_available=DEEP_AVAILABLE)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)