from __future__ import annotations

import base64
import io
import time
import threading
from pathlib import Path
from typing import Iterable, Optional, Sequence

import requests
from PIL import Image, ImageFilter

from app.services.image_studio_queue import CancelledError


def encode_image_for_model(img: Image.Image, max_long_side: int = 1600) -> str:
    if img.mode != "RGB":
        img = img.convert("RGB")
    w, h = img.size
    long_side = max(w, h)
    if long_side > max_long_side and long_side > 0:
        scale = max_long_side / float(long_side)
        nw = max(1, int(round(w * scale)))
        nh = max(1, int(round(h * scale)))
        img = img.resize((nw, nh), Image.LANCZOS)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    image_bytes = buffer.getvalue()
    return base64.b64encode(image_bytes).decode("utf-8")


def _maybe_crop_white_padding(img: Image.Image):
    if img is None:
        return img, None
    try:
        base = img.convert("RGB") if img.mode != "RGB" else img
        w0, h0 = base.size
        if w0 < 80 or h0 < 80:
            return img, None

        max_dim = 420
        scale = min(max_dim / float(max(w0, h0)), 1.0)
        if scale < 1.0:
            small = base.resize((max(1, int(w0 * scale)), max(1, int(h0 * scale))), Image.LANCZOS)
        else:
            small = base
        w, h = small.size
        if w < 40 or h < 40:
            return img, None

        px = small.load()
        stride = 2
        white_thr = 245
        ratio_thr = 0.985

        def is_white(rgb):
            r, g, b = rgb
            return r >= white_thr and g >= white_thr and b >= white_thr

        def row_white_ratio(y: int) -> float:
            total = 0
            white = 0
            for x in range(0, w, stride):
                total += 1
                if is_white(px[x, y]):
                    white += 1
            return (white / float(total)) if total else 0.0

        def col_white_ratio(x: int) -> float:
            total = 0
            white = 0
            for y in range(0, h, stride):
                total += 1
                if is_white(px[x, y]):
                    white += 1
            return (white / float(total)) if total else 0.0

        top = 0
        for y in range(h):
            if row_white_ratio(y) >= ratio_thr:
                top += 1
            else:
                break
        bottom = 0
        for y in range(h - 1, -1, -1):
            if row_white_ratio(y) >= ratio_thr:
                bottom += 1
            else:
                break
        left = 0
        for x in range(w):
            if col_white_ratio(x) >= ratio_thr:
                left += 1
            else:
                break
        right = 0
        for x in range(w - 1, -1, -1):
            if col_white_ratio(x) >= ratio_thr:
                right += 1
            else:
                break

        pad_h = top + bottom
        pad_w = left + right
        if pad_h <= 0 and pad_w <= 0:
            return img, None

        min_pad_ratio = 0.08
        has_tb = (pad_h / float(h)) >= min_pad_ratio and top > 0 and bottom > 0
        has_lr = (pad_w / float(w)) >= min_pad_ratio and left > 0 and right > 0
        if not (has_tb or has_lr):
            return img, None

        if has_tb and abs(top - bottom) > max(4, int(0.22 * pad_h)):
            has_tb = False
        if has_lr and abs(left - right) > max(4, int(0.22 * pad_w)):
            has_lr = False
        if not (has_tb or has_lr):
            return img, None

        crop_left = left if has_lr else 0
        crop_right = right if has_lr else 0
        crop_top = top if has_tb else 0
        crop_bottom = bottom if has_tb else 0

        cw = w - crop_left - crop_right
        ch = h - crop_top - crop_bottom
        if cw < int(0.45 * w) or ch < int(0.45 * h):
            return img, None

        x1 = int(crop_left / float(w) * w0)
        y1 = int(crop_top / float(h) * h0)
        x2 = int((w - crop_right) / float(w) * w0)
        y2 = int((h - crop_bottom) / float(h) * h0)
        x1 = max(0, min(w0 - 1, x1))
        y1 = max(0, min(h0 - 1, y1))
        x2 = max(x1 + 1, min(w0, x2))
        y2 = max(y1 + 1, min(h0, y2))

        cropped = base.crop((x1, y1, x2, y2))
        cw0, ch0 = cropped.size
        if cw0 < 80 or ch0 < 80:
            return img, None

        orig_ratio = w0 / float(h0)
        crop_ratio = cw0 / float(ch0)
        if abs(crop_ratio - 1.0) > 0.08 and abs(crop_ratio - 1.0) >= abs(orig_ratio - 1.0) * 0.7:
            return img, None

        return cropped, {"orig_size": (w0, h0), "cropped_size": (cw0, ch0), "box": (x1, y1, x2, y2)}
    except Exception:
        return img, None


def _check_cancel(cancel_event):
    if cancel_event is not None and cancel_event.is_set():
        raise CancelledError("Job cancelled")


def _post_with_cancel(url: str, payload: dict, headers: dict, timeout: tuple, cancel_event):
    session = requests.Session()
    done = threading.Event()
    box = {}

    def _run():
        try:
            box["resp"] = session.post(url, json=payload, headers=headers, timeout=timeout)
        except Exception as e:
            box["err"] = e
        finally:
            done.set()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    while not done.is_set():
        if cancel_event is not None and cancel_event.is_set():
            try:
                session.close()
            except Exception:
                pass
            raise CancelledError("Job cancelled")
        done.wait(0.25)
    if "err" in box:
        raise box["err"]
    return box.get("resp")


def process_image_with_nano_banana(
    api_key,
    api_base,
    model,
    image_path,
    output_path,
    extra_prompt,
    temperature,
    target_width,
    target_height,
    is_main_image=True,
    prompt_override=None,
    cancel_event=None,
    allow_description_prompt: bool = True,
    reference_image_paths: Optional[Sequence[str]] = None,
):
    try:
        total_start = time.time()
        file_tag = f"[{Path(str(image_path)).name}]"
        prompt = str(prompt_override or extra_prompt or "").strip()

        _check_cancel(cancel_event)

        img = Image.open(image_path)
        img.load()

        cropped_img, crop_info = _maybe_crop_white_padding(img)
        if crop_info:
            img = cropped_img

        _check_cancel(cancel_event)

        send_img = img.convert("RGB") if img.mode != "RGB" else img
        w0, h0 = send_img.size
        if w0 > 0 and h0 > 0:
            target_ratio = 3.0 / 4.0
            cur_ratio = w0 / float(h0)
            if abs(cur_ratio - target_ratio) > 0.005:
                if cur_ratio > target_ratio:
                    canvas_w = w0
                    canvas_h = max(1, int(round(w0 / target_ratio)))
                else:
                    canvas_h = h0
                    canvas_w = max(1, int(round(h0 * target_ratio)))
                sample_points = [
                    (0, 0),
                    (w0 - 1, 0),
                    (0, h0 - 1),
                    (w0 - 1, h0 - 1),
                    (w0 // 2, 0),
                    (w0 // 2, h0 - 1),
                ]
                r_total = 0
                g_total = 0
                b_total = 0
                for x, y in sample_points:
                    pixel = send_img.getpixel((x, y))
                    r_total += pixel[0]
                    g_total += pixel[1]
                    b_total += pixel[2]
                count = len(sample_points)
                bg_color = (r_total // count, g_total // count, b_total // count)
                base_bg = send_img.resize((canvas_w, canvas_h), Image.LANCZOS)
                blurred_bg = base_bg.filter(ImageFilter.GaussianBlur(radius=25))
                color_layer = Image.new("RGB", (canvas_w, canvas_h), bg_color)
                canvas = Image.blend(blurred_bg, color_layer, alpha=0.4)
                offset_x = (canvas_w - w0) // 2
                offset_y = (canvas_h - h0) // 2
                canvas.paste(send_img, (offset_x, offset_y))
                send_img = canvas

        request_max_long_side = 1600
        request_max_bytes = 0

        w0, h0 = send_img.size
        long0 = max(w0, h0)
        if long0 > request_max_long_side and long0 > 0:
            scale0 = request_max_long_side / float(long0)
            nw0 = max(1, int(round(w0 * scale0)))
            nh0 = max(1, int(round(h0 * scale0)))
            send_img = send_img.resize((nw0, nh0), Image.LANCZOS)

        image_bytes = b""
        for _ in range(6):
            buffer = io.BytesIO()
            send_img.save(buffer, format="PNG", optimize=True)
            image_bytes = buffer.getvalue()
            if not request_max_bytes or len(image_bytes) <= request_max_bytes:
                break
            w1, h1 = send_img.size
            long1 = max(w1, h1)
            if long1 <= 256:
                break
            ratio = (request_max_bytes / float(len(image_bytes))) ** 0.5 if request_max_bytes else 0.9
            ratio = max(0.5, min(0.95, ratio * 0.95))
            nw1 = max(1, int(round(w1 * ratio)))
            nh1 = max(1, int(round(h1 * ratio)))
            if nw1 == w1 and nh1 == h1:
                break
            send_img = send_img.resize((nw1, nh1), Image.LANCZOS)

        b64_image = base64.b64encode(image_bytes).decode("utf-8")
        parts = [{"inlineData": {"mimeType": "image/png", "data": b64_image}}]

        ref_paths: Iterable[str] = reference_image_paths or []
        for rp in ref_paths:
            try:
                _check_cancel(cancel_event)
                rp_str = str(rp or "").strip()
                if not rp_str:
                    continue
                ref_img = Image.open(rp_str)
                ref_img.load()
                ref_b64 = encode_image_for_model(ref_img, max_long_side=1200)
                if ref_b64:
                    parts.append({"inlineData": {"mimeType": "image/png", "data": ref_b64}})
            except Exception:
                continue

        parts.append({"text": prompt})

        if not str(api_base or "").strip() or not str(model or "").strip():
            return False, "API base/model missing"

        if not str(api_key or "").strip():
            return False, "API key missing"

        url = f"{str(api_base or '').rstrip('/')}/{model}:generateContent"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {"temperature": temperature},
        }

        max_retries = 2
        last_error = None
        final_response = None
        final_result = None
        final_image_data_part = None
        request_error_text = None

        request_timeout = (20, 240)
        for attempt in range(1, max_retries + 1):
            try:
                _check_cancel(cancel_event)
                response = _post_with_cancel(url, payload, headers, request_timeout, cancel_event)
                if response.status_code == 200:
                    try:
                        result = response.json()
                    except Exception as e:
                        request_error_text = f"Invalid JSON response: {e}"
                        break
                    candidates = result.get("candidates", [])
                    image_data_part = None
                    for candidate in candidates:
                        parts = candidate.get("content", {}).get("parts", [])
                        for part in parts:
                            if "inlineData" in part and isinstance(part.get("inlineData"), dict) and part["inlineData"].get("data"):
                                image_data_part = part["inlineData"]
                                break
                        if image_data_part:
                            break
                    if not image_data_part:
                        request_error_text = "No image data found in response"
                        break
                    final_response = response
                    final_result = result
                    final_image_data_part = image_data_part
                    break
                request_error_text = f"Error code: {response.status_code} - {response.text}"
                if response.status_code >= 500 and attempt < max_retries:
                    time.sleep(5 * attempt)
                    continue
                break
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                last_error = e
                if attempt < max_retries:
                    time.sleep(5 * attempt)
                    continue
                request_error_text = f"Request error after retries: {e}"
                break
            except requests.exceptions.RequestException as e:
                request_error_text = f"Request exception: {e}"
                break

        if final_response is None or final_image_data_part is None:
            if request_error_text:
                return False, request_error_text
            if last_error is not None:
                return False, f"Request error after retries: {last_error}"
            return False, "Unknown request error"

        _check_cancel(cancel_event)
        img_bytes = base64.b64decode(final_image_data_part["data"])
        img = Image.open(io.BytesIO(img_bytes))

        suffix = Path(str(output_path)).suffix.lower()
        target_size = (int(target_width), int(target_height))
        if target_size[0] > 0 and target_size[1] > 0 and img.size != target_size:
            tw, th = target_size
            iw, ih = img.size
            if iw > 0 and ih > 0:
                target_ratio = tw / float(th)
                img_ratio = iw / float(ih)
                if abs(img_ratio - target_ratio) <= 0.002:
                    img = img.resize((tw, th), Image.LANCZOS)
                else:
                    has_alpha = suffix == ".png" and "A" in img.getbands()
                    base = img.convert("RGBA") if has_alpha else img.convert("RGB")
                    scale = max(tw / float(iw), th / float(ih))
                    new_w = max(1, int(round(iw * scale)))
                    new_h = max(1, int(round(ih * scale)))
                    resized = base.resize((new_w, new_h), Image.LANCZOS)
                    left = max(0, (new_w - tw) // 2)
                    top = max(0, (new_h - th) // 2)
                    right = min(new_w, left + tw)
                    bottom = min(new_h, top + th)
                    img = resized.crop((left, top, right, bottom))

        _check_cancel(cancel_event)
        if suffix in {".jpg", ".jpeg"}:
            if img.mode not in {"RGB", "L"}:
                img = img.convert("RGB")
            img.save(output_path, format="JPEG", quality=95, optimize=True, progressive=True)
        elif suffix == ".webp":
            img.save(output_path, format="WEBP", quality=95, method=6)
        elif suffix == ".png":
            img.save(output_path, format="PNG", optimize=True)
        elif suffix == ".bmp":
            if img.mode not in {"RGB", "L"}:
                img = img.convert("RGB")
            img.save(output_path, format="BMP")
        elif suffix == ".gif":
            img.save(output_path, format="GIF")
        else:
            img.save(output_path)

        total_end = time.time()
        _ = total_end - total_start
        return True, f"Image processed: {output_path}"
    except Exception as e:
        return False, str(e)
