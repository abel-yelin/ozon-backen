from __future__ import annotations

import time
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED

import requests
from PIL import Image

from app.services.storage import R2Service
from app.services.image_studio_queue import check_cancelled, get_cancel_event, run_in_job_context, capture_job_context
from app.core.config import settings

from app.services.image_studio_engine import (
    process_image_with_nano_banana,
    encode_image_for_model,
)


def _safe_filename_from_url(url: str) -> str:
    if not url:
        return ""
    try:
        name = url.split("?")[0].split("/")[-1]
        return name or ""
    except Exception:
        return ""


def _stem_from_name(name: str) -> str:
    if not name:
        return ""
    base = name.split("/")[-1]
    dot = base.rfind(".")
    return base[:dot] if dot > 0 else base


def _is_main_stem(stem: str) -> bool:
    if not stem:
        return False
    return stem.split("_")[-1] == "1"


def _download_to_file(url: str, path: Path) -> None:
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()
    path.write_bytes(resp.content)


def _read_image_bytes(path: Path) -> bytes:
    return path.read_bytes()


def _infer_content_type(fmt: str) -> str:
    f = fmt.lower()
    if f in {"jpg", "jpeg"}:
        return "image/jpeg"
    if f == "webp":
        return "image/webp"
    if f == "png":
        return "image/png"
    return "application/octet-stream"


def _upload_output(r2: R2Service, data: bytes, key: str, fmt: str) -> str:
    content_type = _infer_content_type(fmt)
    return r2.upload_bytes_sync(data=data, key=key, content_type=content_type)


def _encode_style_prompt(
    image_path: Path,
    api_key: str,
    api_base: str,
    model: str,
    instruction: str,
) -> str:
    if not instruction:
        return ""
    img = Image.open(image_path).convert("RGB")
    b64_image = encode_image_for_model(img, max_long_side=1600)
    url = f"{api_base.rstrip('/')}/{model}:generateContent"
    payload = {
        "contents": [
            {
                "parts": [
                    {"inlineData": {"mimeType": "image/png", "data": b64_image}},
                    {"text": instruction},
                ]
            }
        ],
        "generationConfig": {"temperature": 0.3},
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    response = requests.post(url, json=payload, headers=headers, timeout=240)
    if response.status_code != 200:
        return ""
    data = response.json() or {}
    candidates = data.get("candidates") or []
    if not candidates:
        return ""
    parts = (candidates[0].get("content") or {}).get("parts") or []
    texts = []
    for part in parts:
        if "text" in part:
            texts.append(str(part["text"]))
    return "".join(texts).strip()


def _pick_prompt(templates: Dict[str, str], key_cn: str, use_english: bool) -> str:
    if use_english:
        en_key = key_cn.replace("_cn", "_en") if key_cn.endswith("_cn") else key_cn + "_en"
        value = str(templates.get(en_key) or "").strip()
        if value:
            return value
    return str(templates.get(key_cn) or "").strip()


def _build_batch_prompt(
    templates: Dict[str, str],
    is_main: bool,
    extra_prompt: str,
    use_english: bool,
) -> str:
    segments = []
    common = _pick_prompt(templates, "common_cn", use_english)
    if common:
        segments.append(common)
    role = _pick_prompt(templates, "main_cn" if is_main else "secondary_cn", use_english)
    if role:
        segments.append(role)
    title_details = _pick_prompt(templates, "title_details_prompt_cn", use_english)
    if title_details:
        segments.append(title_details)
    if extra_prompt:
        segments.append(extra_prompt)
    return "\n\n".join([s for s in segments if s]).strip()


def _build_optimize_prompt(
    templates: Dict[str, str],
    options: Dict[str, Any],
    use_english: bool,
) -> str:
    segments = []
    extra = str(options.get("extra_prompt") or "").strip()
    if extra:
        segments.append(extra)
    if options.get("remove_watermark"):
        segments.append(_pick_prompt(templates, "opt_remove_watermark_cn", use_english))
    if options.get("remove_logo"):
        segments.append(_pick_prompt(templates, "opt_remove_logo_cn", use_english))
    if options.get("text_edit"):
        segments.append(_pick_prompt(templates, "opt_text_edit_cn", use_english))
    if options.get("restructure"):
        segments.append(_pick_prompt(templates, "opt_restructure_cn", use_english))
    if options.get("recolor"):
        segments.append(_pick_prompt(templates, "opt_recolor_cn", use_english))
    if options.get("add_markers"):
        segments.append(_pick_prompt(templates, "opt_add_markers_cn", use_english))
    return "\n\n".join([s for s in segments if s]).strip()


def _build_custom_prompt(
    templates: Dict[str, str],
    options: Dict[str, Any],
    is_main: bool,
    style_prompt: str,
    use_english: bool,
) -> str:
    segments = []
    if options.get("include_common"):
        segments.append(_pick_prompt(templates, "common_cn", use_english))
    if options.get("include_role"):
        segments.append(_pick_prompt(templates, "main_cn" if is_main else "secondary_cn", use_english))
    if options.get("include_title_details"):
        segments.append(_pick_prompt(templates, "title_details_prompt_cn", use_english))
    if options.get("include_style") and style_prompt:
        segments.append(style_prompt)
    if options.get("remove_watermark"):
        segments.append(_pick_prompt(templates, "opt_remove_watermark_cn", use_english))
    if options.get("remove_logo"):
        segments.append(_pick_prompt(templates, "opt_remove_logo_cn", use_english))
    extra = str(options.get("extra_prompt") or "").strip()
    if extra:
        segments.append(extra)
    plan_seg = str(options.get("plan_segment") or "").strip()
    if options.get("include_plan") and plan_seg:
        segments.append(plan_seg)
    return "\n\n".join([s for s in segments if s]).strip()


def _build_metadata(output_path: Path) -> Dict[str, Any]:
    meta: Dict[str, Any] = {}
    try:
        img = Image.open(output_path)
        meta["width"] = img.width
        meta["height"] = img.height
    except Exception:
        pass
    try:
        meta["size_bytes"] = output_path.stat().st_size
    except Exception:
        pass
    return meta


def _process_single_image(
    api_key: str,
    api_base: str,
    model: str,
    target_width: int,
    target_height: int,
    temperature: float,
    prompt_override: str,
    source_url: str,
    output_key: str,
    output_format: str,
    is_main: bool,
    allow_description_prompt: bool = False,
    reference_urls: Optional[List[str]] = None,
) -> Tuple[str, Dict[str, Any]]:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir_path = Path(temp_dir)
        suffix = "." + (output_format or "png").lstrip(".")
        source_path = temp_dir_path / ("input" + suffix)
        output_path = temp_dir_path / ("output" + suffix)

        check_cancelled()
        _download_to_file(source_url, source_path)
        check_cancelled()

        reference_paths = []
        if reference_urls:
            for idx, ref_url in enumerate(reference_urls):
                ref_path = temp_dir_path / f"ref_{idx}{suffix}"
                _download_to_file(ref_url, ref_path)
                reference_paths.append(str(ref_path))

        ok, msg = process_image_with_nano_banana(
            api_key,
            api_base,
            model,
            str(source_path),
            str(output_path),
            "",
            temperature,
            target_width,
            target_height,
            is_main,
            prompt_override=prompt_override,
            cancel_event=get_cancel_event(),
            allow_description_prompt=allow_description_prompt,
            reference_image_paths=reference_paths or None,
        )

        if not ok:
            raise RuntimeError(msg or "image processing failed")

        r2 = R2Service()
        output_bytes = _read_image_bytes(output_path)
        output_url = r2.upload_bytes_sync(
            data=output_bytes,
            key=output_key,
            content_type=_infer_content_type(output_format),
        )
        meta = _build_metadata(output_path)
        return output_url, meta


def _process_batch_concurrent(
    sku_images_map: Dict[str, List[Dict[str, Any]]],
    do_main: bool,
    do_secondary: bool,
    max_workers_main: int,
    max_workers_secondary: int,
    api_key: str,
    api_base: str,
    model: str,
    target_width: int,
    target_height: int,
    temperature: float,
    output_format: str,
    templates: Dict[str, str],
    use_english: bool,
    options: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Process batch images concurrently using ThreadPoolExecutor (two-stage approach)."""
    all_results = []
    ctx = capture_job_context()

    # Stage 1: Process main images concurrently
    main_results = []
    main_success = 0
    main_failed = 0

    def _process_sku_main(sku_name: str, sources: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Process main image for a single SKU."""
        check_cancelled()
        if not sources:
            return {"sku": sku_name, "ok": False, "error": "No sources"}

        sources_sorted = sorted(sources, key=lambda s: str(s.get("name") or s.get("url") or ""))

        # Find main image (ending with "_1")
        head = None
        for item in sources_sorted:
            stem_value = item.get("stem") or _stem_from_name(str(item.get("name") or ""))
            if _is_main_stem(stem_value):
                head = item
                break
        if head is None:
            head = sources_sorted[0]

        if not head:
            return {"sku": sku_name, "ok": False, "error": "No head image"}

        # Process main image
        is_main = True
        prompt_override = _build_batch_prompt(templates, is_main, str(options.get("extra_prompt") or ""), use_english)
        if not prompt_override:
            prompt_override = str(options.get("extra_prompt") or "")

        output_key = f"image-studio/{sku_name}/{_stem_from_name(head.get('name') or _safe_filename_from_url(head.get('url') or ''))}_{int(time.time())}.{output_format}"

        try:
            output_url, meta = _process_single_image(
                api_key,
                api_base,
                model,
                target_width,
                target_height,
                temperature,
                prompt_override,
                str(head.get("url") or ""),
                output_key,
                output_format,
                is_main,
            )
            return {
                "sku": sku_name,
                "ok": True,
                "source_url": head.get("url"),
                "result_url": output_url,
                "metadata": meta,
                "sources": sources,  # Pass for secondary processing
            }
        except Exception as e:
            return {"sku": sku_name, "ok": False, "error": str(e), "sources": sources}

    # Stage 1: Submit all main image tasks
    if do_main:
        print(f"[Batch] Stage 1: Processing {len(sku_images_map)} SKUs with {max_workers_main} workers", flush=True)
        futures = {}
        with ThreadPoolExecutor(max_workers=max_workers_main) as executor:
            for sku_name, sources in sku_images_map.items():
                check_cancelled()
                print(f"[Batch Main] Submitting: {sku_name}", flush=True)
                future = executor.submit(run_in_job_context, ctx, _process_sku_main, str(sku_name), list(sources or []))
                futures[future] = sku_name

            pending = set(futures.keys())
            try:
                while pending:
                    check_cancelled()
                    done, pending = wait(pending, timeout=0.25, return_when=FIRST_COMPLETED)
                    for future in done:
                        sku_name = futures.get(future) or ""
                        try:
                            r = future.result()
                        except Exception as e:
                            r = {"sku": sku_name, "ok": False, "error": str(e)}
                        main_results.append(r)
                        if r.get("ok"):
                            main_success += 1
                            print(f"[Batch Main] {sku_name} ✓ Success", flush=True)
                        else:
                            main_failed += 1
                            print(f"[Batch Main] {sku_name} ✗ Failed: {r.get('error')}", flush=True)
            finally:
                for f in pending:
                    try:
                        f.cancel()
                    except Exception:
                        pass

        print(f"[Batch] Stage 1 complete: {main_success} success, {main_failed} failed", flush=True)
        all_results.extend([r for r in main_results if r.get("ok")])
    else:
        # If not processing main, just pass through all sources
        for sku_name, sources in sku_images_map.items():
            main_results.append({"sku": sku_name, "ok": True, "sources": sources})

    # Stage 2: Process secondary images concurrently
    secondary_results = []
    secondary_success = 0
    secondary_failed = 0

    if do_secondary:
        # Collect all secondary images from successful SKUs
        secondary_tasks = []

        for result in main_results:
            if not result.get("ok"):
                continue
            sku_name = result.get("sku")
            sources = result.get("sources") or []
            if not sources:
                continue

            sources_sorted = sorted(sources, key=lambda s: str(s.get("name") or s.get("url") or ""))

            # Find main image to exclude
            head = None
            for item in sources_sorted:
                stem_value = item.get("stem") or _stem_from_name(str(item.get("name") or ""))
                if _is_main_stem(stem_value):
                    head = item
                    break
            if head is None:
                head = sources_sorted[0]

            # Extract style prompt from main result if available
            style_prompt = ""
            if result.get("result_url") and options.get("include_style_prompt"):
                instruction = _pick_prompt(templates, "style_extract_instruction_cn", use_english)
                if instruction:
                    try:
                        with tempfile.TemporaryDirectory() as temp_dir:
                            temp_path = Path(temp_dir) / f"head.{output_format}"
                            _download_to_file(result["result_url"], temp_path)
                            style_prompt = _encode_style_prompt(temp_path, api_key, api_base, model, instruction)
                    except Exception:
                        pass

            # Collect secondary images
            for item in sources_sorted:
                if item is head:
                    continue
                secondary_tasks.append((sku_name, item, style_prompt))

        if secondary_tasks:
            max_sec_workers = min(max_workers_secondary, len(secondary_tasks))
            print(f"[Batch] Stage 2: Processing {len(secondary_tasks)} secondary images with {max_sec_workers} workers", flush=True)

            def _process_one_secondary(sku_name: str, item: Dict[str, Any], style_prompt: str) -> Dict[str, Any]:
                """Process a single secondary image."""
                check_cancelled()
                stem_value = item.get("stem") or _stem_from_name(str(item.get("name") or ""))
                is_main = _is_main_stem(stem_value)

                prompt_override = _build_batch_prompt(templates, is_main, str(options.get("extra_prompt") or ""), use_english)
                if style_prompt:
                    prompt_override = "\n\n".join([prompt_override, style_prompt]).strip()

                output_key = f"image-studio/{sku_name}/{_stem_from_name(item.get('name') or _safe_filename_from_url(item.get('url') or ''))}_{int(time.time())}.{output_format}"

                try:
                    output_url, meta = _process_single_image(
                        api_key,
                        api_base,
                        model,
                        target_width,
                        target_height,
                        temperature,
                        prompt_override,
                        str(item.get("url") or ""),
                        output_key,
                        output_format,
                        is_main,
                    )
                    return {
                        "sku": sku_name,
                        "ok": True,
                        "source_url": item.get("url"),
                        "result_url": output_url,
                        "metadata": meta,
                    }
                except Exception as e:
                    return {"sku": sku_name, "ok": False, "error": str(e)}

            futures = {}
            with ThreadPoolExecutor(max_workers=max_sec_workers) as executor:
                for sku_name, item, style_prompt in secondary_tasks:
                    check_cancelled()
                    rel = f"{sku_name}/{item.get('name', '')}"
                    print(f"[Batch Secondary] Submitting: {rel}", flush=True)
                    future = executor.submit(run_in_job_context, ctx, _process_one_secondary, sku_name, item, style_prompt)
                    futures[future] = (sku_name, item.get("name", ""))

                pending = set(futures.keys())
                try:
                    while pending:
                        check_cancelled()
                        done, pending = wait(pending, timeout=0.25, return_when=FIRST_COMPLETED)
                        for future in done:
                            sku_name, name = futures.get(future) or ("", "")
                            rel = f"{sku_name}/{name}" if sku_name else name
                            try:
                                r = future.result()
                            except Exception as e:
                                r = {"sku": sku_name, "ok": False, "error": str(e)}
                            secondary_results.append(r)
                            if r.get("ok"):
                                secondary_success += 1
                                print(f"[Batch Secondary] {rel} ✓ Success", flush=True)
                            else:
                                secondary_failed += 1
                                print(f"[Batch Secondary] {rel} ✗ Failed: {r.get('error')}", flush=True)
                finally:
                    for f in pending:
                        try:
                            f.cancel()
                        except Exception:
                            pass

            print(f"[Batch] Stage 2 complete: {secondary_success} success, {secondary_failed} failed", flush=True)
            all_results.extend([r for r in secondary_results if r.get("ok")])

    print(f"[Batch] All stages complete: {len(all_results)} images processed", flush=True)
    return all_results


def run_image_studio_job(payload: Dict[str, Any]) -> Dict[str, Any]:
    check_cancelled()
    mode = str(payload.get("mode") or "").strip()
    sku = str(payload.get("sku") or "").strip()
    stem = str(payload.get("stem") or "").strip()
    options = payload.get("options") or {}

    ai_defaults = settings.plugins_config.get("ai", {})
    api_key = str(ai_defaults.get("api_key") or options.get("api_key") or "")
    api_base = str(ai_defaults.get("api_base") or options.get("api_base") or "https://llmxapi.com/v1beta")
    model = str(ai_defaults.get("model") or options.get("model") or "models/gemini-2.5-flash-image-preview")
    target_width = int(ai_defaults.get("target_width") or options.get("target_width") or 1500)
    target_height = int(ai_defaults.get("target_height") or options.get("target_height") or 2000)
    temperature = float(ai_defaults.get("default_temperature") or options.get("default_temperature") or 0.5)
    output_format = str(options.get("output_format") or "png").lower()
    templates = options.get("prompt_templates") or {}
    use_english = bool(options.get("use_english"))

    results = []

    def _process_images_for_sku(sku_name: str, sources: List[Dict[str, Any]], do_main: bool, do_secondary: bool):
        nonlocal results
        if not sources:
            return
        sources_sorted = sorted(sources, key=lambda s: str(s.get("name") or s.get("url") or ""))
        head = None
        for item in sources_sorted:
            stem_value = item.get("stem") or _stem_from_name(str(item.get("name") or ""))
            if _is_main_stem(stem_value):
                head = item
                break
        if head is None:
            head = sources_sorted[0]

        style_prompt = ""
        head_output_url = None
        if do_main and head:
            is_main = True
            prompt_override = _build_batch_prompt(templates, is_main, str(options.get("extra_prompt") or ""), use_english)
            if not prompt_override:
                prompt_override = str(options.get("extra_prompt") or "")
            output_key = f"image-studio/{sku_name}/{_stem_from_name(head.get('name') or _safe_filename_from_url(head.get('url') or ''))}_{int(time.time())}.{output_format}"
            output_url, meta = _process_single_image(
                api_key,
                api_base,
                model,
                target_width,
                target_height,
                temperature,
                prompt_override,
                str(head.get("url") or ""),
                output_key,
                output_format,
                is_main,
            )
            head_output_url = output_url
            results.append({
                "sku": sku_name,
                "source_url": head.get("url"),
                "result_url": output_url,
                "metadata": meta,
            })
            if options.get("include_style_prompt"):
                instruction = _pick_prompt(templates, "style_extract_instruction_cn", use_english)
                if instruction:
                    with tempfile.TemporaryDirectory() as temp_dir:
                        temp_path = Path(temp_dir) / f"head.{output_format}"
                        _download_to_file(output_url, temp_path)
                        style_prompt = _encode_style_prompt(temp_path, api_key, api_base, model, instruction)

        for item in sources_sorted:
            if item is head:
                continue
            stem_value = item.get("stem") or _stem_from_name(str(item.get("name") or ""))
            is_main = _is_main_stem(stem_value)
            if is_main and not do_main:
                continue
            if (not is_main) and not do_secondary:
                continue
            prompt_override = _build_batch_prompt(templates, is_main, str(options.get("extra_prompt") or ""), use_english)
            if style_prompt and (not is_main):
                prompt_override = "\n\n".join([prompt_override, style_prompt]).strip()
            output_key = f"image-studio/{sku_name}/{_stem_from_name(item.get('name') or _safe_filename_from_url(item.get('url') or ''))}_{int(time.time())}.{output_format}"
            output_url, meta = _process_single_image(
                api_key,
                api_base,
                model,
                target_width,
                target_height,
                temperature,
                prompt_override,
                str(item.get("url") or ""),
                output_key,
                output_format,
                is_main,
            )
            results.append({
                "sku": sku_name,
                "source_url": item.get("url"),
                "result_url": output_url,
                "metadata": meta,
            })

        return head_output_url

    if mode in {"batch_main_generate", "batch_secondary_generate", "batch_series_generate"}:
        sku_images_map = options.get("sku_images_map") or {}

        # Get max_workers from options or config, with limits
        ai_defaults = settings.plugins_config.get("ai", {})
        default_workers = int(ai_defaults.get("image_workers", 30))

        max_workers_main = 0
        try:
            max_workers_main = int(options.get("max_workers_main") or options.get("max_workers") or 0)
        except Exception:
            max_workers_main = 0
        if max_workers_main <= 0:
            max_workers_main = default_workers
        if max_workers_main < 1:
            max_workers_main = 1
        if max_workers_main > 60:
            max_workers_main = 60

        max_workers_secondary = 0
        try:
            max_workers_secondary = int(options.get("max_workers_secondary") or options.get("max_workers") or 0)
        except Exception:
            max_workers_secondary = 0
        if max_workers_secondary <= 0:
            max_workers_secondary = default_workers
        if max_workers_secondary < 1:
            max_workers_secondary = 1
        if max_workers_secondary > 60:
            max_workers_secondary = 60

        sku_list = list(sku_images_map.keys())
        if len(sku_list) == 0:
            return {"mode": mode, "items": []}

        # Limit workers to number of SKUs
        if max_workers_main > len(sku_list):
            max_workers_main = len(sku_list)

        do_main = mode in {"batch_main_generate", "batch_series_generate"}
        do_secondary = mode in {"batch_secondary_generate", "batch_series_generate"}

        # Process batch with concurrent workers
        batch_results = _process_batch_concurrent(
            sku_images_map=sku_images_map,
            do_main=do_main,
            do_secondary=do_secondary,
            max_workers_main=max_workers_main,
            max_workers_secondary=max_workers_secondary,
            api_key=api_key,
            api_base=api_base,
            model=model,
            target_width=target_width,
            target_height=target_height,
            temperature=temperature,
            output_format=output_format,
            templates=templates,
            use_english=use_english,
            options=options,
        )

        return {"mode": mode, "items": batch_results}

    if mode == "folder_generate":
        sources = options.get("source_images") or []
        do_main = bool(options.get("do_main", True))
        do_secondary = bool(options.get("do_secondary", True))
        _process_images_for_sku(sku, list(sources), do_main, do_secondary)
        return {"mode": mode, "items": results}

    if mode in {"image_regenerate", "image_optimize_current", "image_custom_generate"}:
        source_url = str(options.get("source_url") or "")
        if not source_url:
            raise ValueError("source_url required")
        stem_value = stem or _stem_from_name(_safe_filename_from_url(source_url))
        is_main = _is_main_stem(stem_value)
        style_prompt = ""
        if options.get("include_style") and (not is_main):
            instruction = _pick_prompt(templates, "style_extract_instruction_cn", use_english)
            if instruction:
                with tempfile.TemporaryDirectory() as temp_dir:
                    temp_path = Path(temp_dir) / f"head.{output_format}"
                    _download_to_file(source_url, temp_path)
                    style_prompt = _encode_style_prompt(temp_path, api_key, api_base, model, instruction)

        if mode == "image_optimize_current":
            prompt_override = _build_optimize_prompt(templates, options, use_english)
        elif mode == "image_custom_generate":
            prompt_override = _build_custom_prompt(templates, options, is_main, style_prompt, use_english)
        else:
            prompt_override = _build_batch_prompt(templates, is_main, str(options.get("extra_prompt") or ""), use_english)

        if not prompt_override:
            prompt_override = str(options.get("extra_prompt") or "")

        output_key = f"image-studio/{sku or 'single'}/{stem_value}_{int(time.time())}.{output_format}"
        output_url, meta = _process_single_image(
            api_key,
            api_base,
            model,
            target_width,
            target_height,
            temperature,
            prompt_override,
            source_url,
            output_key,
            output_format,
            is_main,
            allow_description_prompt=False,
            reference_urls=options.get("reference_urls"),
        )

        results.append({
            "sku": sku,
            "source_url": source_url,
            "result_url": output_url,
            "metadata": meta,
        })
        return {"mode": mode, "items": results}

    raise ValueError(f"Unknown mode: {mode}")
