import os
import tempfile
import random

from PyQt5.QtCore import QObject, pyqtSignal
from core.config_loader import device_config


class ScanWorker(QObject):
    finished = pyqtSignal()
    success = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, session_number, parent=None):
        super().__init__(parent)
        self.session_number = session_number

    def _image_to_pdf(self, img_path: str) -> str | None:
        """Convert a scanned image file to a single-page PDF.
        - Always uses US Letter page size.
        - Preserves the original image aspect ratio; never stretches or widens.
        - Only scales down to fit within margins (no upscaling of smaller images).
        - Uses 300 DPI where applicable.
        Returns PDF path or None.
        """
        # First, try reportlab for best control
        try:
            from reportlab.pdfgen import canvas
            from reportlab.lib.pagesizes import letter
            from reportlab.lib.utils import ImageReader

            pdf_path = os.path.splitext(img_path)[0] + ".pdf"
            c = canvas.Canvas(pdf_path, pagesize=letter)
            page_w, page_h = letter

            img = ImageReader(img_path)
            iw, ih = img.getSize()
            # Fit within 0.5 inch margins, preserving aspect ratio
            margin = 36  # points
            avail_w = page_w - 2 * margin
            avail_h = page_h - 2 * margin
            # Do not upscale if the image is smaller than the available area
            scale = min(1.0, min(avail_w / iw, avail_h / ih))
            dw = iw * scale
            dh = ih * scale
            x = (page_w - dw) / 2
            y = (page_h - dh) / 2
            c.drawImage(img, x, y, dw, dh)
            c.showPage()
            c.save()
            return pdf_path
        except Exception:
            pass
        # Fallback: Pillow direct save to PDF at 300 DPI
        try:
            from PIL import Image
            im = Image.open(img_path)
            if im.mode not in ("RGB", "L"):
                im = im.convert("RGB")
            pdf_path = os.path.splitext(img_path)[0] + ".pdf"
            im.save(pdf_path, "PDF", resolution=300.0)
            return pdf_path
        except Exception:
            return None

    def run(self):
        # Perform scanning via Windows WIA in a worker thread, with device auto-select and persistence
        try:
            import pythoncom
            pythoncom.CoInitialize()
            try:
                from win32com.client import Dispatch
            except Exception:
                Dispatch = None

            if Dispatch is None:
                raise Exception("Scanning not available: pywin32 (win32com) is not installed.")

            cdlg = Dispatch("WIA.CommonDialog")
            # WIA image format GUIDs and preference
            FORMAT_GUIDS = {
                "JPEG": "{B96B3CAE-0728-11D3-9D7B-0000F81EF32E}",
                "PNG":  "{B96B3CAF-0728-11D3-9D7B-0000F81EF32E}",
                "BMP":  "{B96B3CAB-0728-11D3-9D7B-0000F81EF32E}",
                "TIFF": "{B96B3CB1-0728-11D3-9D7B-0000F81EF32E}",
            }
            PREFERRED_FORMATS = [
                FORMAT_GUIDS["JPEG"],
                FORMAT_GUIDS["PNG"],
                FORMAT_GUIDS["BMP"],
                FORMAT_GUIDS["TIFF"],
            ]

            def _get_supported_format_guids(wia_item):
                guids = []
                try:
                    fmts = getattr(wia_item, "Formats", None)
                    if fmts is not None:
                        count = int(getattr(fmts, "Count", 0) or 0)
                        for i in range(1, count + 1):
                            try:
                                guid = fmts.Item(i)
                                if isinstance(guid, str):
                                    guids.append(guid.upper())
                            except Exception:
                                pass
                except Exception:
                    pass
                return guids

            device = None
            # Try to locate/persist device selection
            try:
                dm = Dispatch("WIA.DeviceManager")
                infos = dm.DeviceInfos
                count = int(getattr(infos, "Count", 0) or 0)

                def _connect_info(info):
                    try:
                        return info.Connect()
                    except Exception:
                        return None

                saved_id = device_config.get("Scanner", "selected_device_id", "")
                saved_name = device_config.get("Scanner", "selected_device_name", "")

                if count == 1:
                    info = infos.Item(1)
                    device = _connect_info(info)
                    # Persist this as the default
                    try:
                        device_config.set("Scanner", "selected_device_id", getattr(info, "DeviceID", ""))
                        device_config.set("Scanner", "selected_device_name", getattr(info, "Properties", {}).Item("Name").Value if hasattr(info, "Properties") else "")
                        # Default preferred DPI
                        if not device_config.get("Scanner", "resolution_dpi", ""):
                            device_config.set("Scanner", "resolution_dpi", "300")
                        device_config.save()
                    except Exception:
                        pass
                elif count > 1:
                    # Try saved selection first
                    if saved_id or saved_name:
                        # Search by DeviceID or Name
                        for i in range(1, count + 1):
                            info = infos.Item(i)
                            did = getattr(info, "DeviceID", "")
                            name = ""
                            try:
                                name = info.Properties.Item("Name").Value
                            except Exception:
                                name = ""
                            if (saved_id and did == saved_id) or (saved_name and name == saved_name):
                                device = _connect_info(info)
                                break
                    if device is None:
                        # Prompt user once to select, persist, then proceed headless next time
                        try:
                            sel = cdlg.ShowSelectDevice(1, True, False)
                            if sel is not None:
                                # Persist selection
                                try:
                                    # sel is a Device; try to read its DeviceID via sel.Properties
                                    did = ""
                                    try:
                                        did = sel.Properties.Item("DeviceID").Value
                                    except Exception:
                                        did = getattr(sel, "DeviceID", "")
                                    name = ""
                                    try:
                                        name = sel.Properties.Item("Name").Value
                                    except Exception:
                                        name = getattr(sel, "Name", "")
                                    device_config.set("Scanner", "selected_device_id", did or "")
                                    device_config.set("Scanner", "selected_device_name", name or "")
                                    if not device_config.get("Scanner", "resolution_dpi", ""):
                                        device_config.set("Scanner", "resolution_dpi", "300")
                                    device_config.save()
                                except Exception:
                                    pass
                                device = sel
                        except Exception:
                            device = None
                # else: no devices -> handled below
            except Exception:
                device = None

            img_path = None

            outputs = []

            if device is not None:
                # Headless transfer using current device settings; set DPI if possible
                try:
                    # Try to set resolution on the device's first item
                    item = device.Items.Item(1) if hasattr(device.Items, "Item") else device.Items[1]


                    # Use scanner's default settings; do not override WIA properties

                    # Transfer pages in a loop until feeder is empty or an unrecoverable error occurs
                    temp_dir = tempfile.gettempdir()
                    base = f"scan_{self.session_number}_{os.getpid()}_{random.randint(1000, 9999)}"
                    page_index = 1
                    while True:
                        try:
                            # Try multiple transfer formats in order of preference; fall back on parameter errors
                            supported = [g for g in _get_supported_format_guids(item)]
                            candidates = [g for g in PREFERRED_FORMATS if g.upper() in supported] or PREFERRED_FORMATS
                            image = None
                            last_param_exc = None
                            for fmt in candidates:
                                try:
                                    image = cdlg.ShowTransfer(item, fmt)
                                    last_param_exc = None
                                    break
                                except Exception as fe:
                                    msgf = str(fe) or ""
                                    hrf = getattr(fe, "hresult", None)
                                    if hrf in (-2147024809, 0x80070057) or "parameter is incorrect" in msgf.lower():
                                        # Unsupported format or bad parameter for this device; try next format
                                        last_param_exc = fe
                                        continue
                                    else:
                                        # Other errors bubble to outer handler
                                        raise
                            if image is None and last_param_exc is not None:
                                # Exhausted candidates; raise last param error for outer handling
                                raise last_param_exc
                        except Exception as he:
                            # If no pages left in feeder, break gracefully
                            msg = str(he) or ""
                            # Detect by HRESULT when available (WIA_ERROR_PAPER_EMPTY = 0x80210003)
                            try:
                                hresult = getattr(he, "hresult", None)
                            except Exception:
                                hresult = None
                            lowercase = msg.lower()
                            if (
                                hresult in (-2145320957, 0x80210003)
                                or "wia_error_paper_empty" in lowercase
                                or "there are no pages to scan" in lowercase
                                or ("feeder" in lowercase and "empty" in lowercase)
                                or "no documents left in the document feeder" in lowercase
                                or ("user requested a scan" in lowercase and "no documents" in lowercase and "feeder" in lowercase)
                                or "no documents" in lowercase
                            ):
                                break
                            # Otherwise, stop without opening any settings UI
                            raise Exception(msg or "Scan failed.")

                        if image is None:
                            # No more images
                            break

                        # Save this page
                        img_path = os.path.join(temp_dir, f"{base}_p{page_index:03d}.jpg")
                        try:
                            image.SaveFile(img_path)
                        except Exception as e:
                            # If saving fails mid-batch, stop and report what we have
                            if not outputs:
                                raise Exception(f"Failed to save scanned image: {e}")
                            break

                        # Auto-crop margins to remove scanner platen/gray borders before conversion
                        try:
                            cropped_path = self._auto_crop_margins(img_path)
                            use_img_path = cropped_path or img_path
                        except Exception:
                            use_img_path = img_path

                        # Convert to PDF for consistency with previews and sending pipeline
                        pdf_path = self._image_to_pdf(use_img_path)
                        out_path = pdf_path if pdf_path else use_img_path
                        outputs.append(out_path)

                        page_index += 1

                    if not outputs:
                        self.error.emit("No pages scanned.")
                        return

                except Exception as he:
                    # Do not show settings UI; report error
                    self.error.emit(str(he))
                    return
            else:
                # No device found via manager; prompt once to select a device, then scan with defaults
                try:
                    sel = cdlg.ShowSelectDevice(1, True, False)
                except Exception as e:
                    raise Exception(str(e))
                if sel is None:
                    self.error.emit("No scanner selected.")
                    return
                # Attempt to persist selection for next time
                try:
                    did = ""
                    try:
                        did = sel.Properties.Item("DeviceID").Value
                    except Exception:
                        did = getattr(sel, "DeviceID", "")
                    name = ""
                    try:
                        name = sel.Properties.Item("Name").Value
                    except Exception:
                        name = getattr(sel, "Name", "")
                    device_config.set("Scanner", "selected_device_id", did or "")
                    device_config.set("Scanner", "selected_device_name", name or "")
                    device_config.save()
                except Exception:
                    pass
                # Perform transfer loop with defaults
                try:
                    item = sel.Items.Item(1) if hasattr(sel.Items, "Item") else sel.Items[1]
                    temp_dir = tempfile.gettempdir()
                    base = f"scan_{self.session_number}_{os.getpid()}_{random.randint(1000, 9999)}"
                    page_index = 1
                    while True:
                        try:
                            # Try multiple transfer formats in order of preference; fall back on parameter errors
                            supported = [g for g in _get_supported_format_guids(item)]
                            candidates = [g for g in PREFERRED_FORMATS if g.upper() in supported] or PREFERRED_FORMATS
                            image = None
                            last_param_exc = None
                            for fmt in candidates:
                                try:
                                    image = cdlg.ShowTransfer(item, fmt)
                                    last_param_exc = None
                                    break
                                except Exception as fe:
                                    msgf = str(fe) or ""
                                    hrf = getattr(fe, "hresult", None)
                                    if hrf in (-2147024809, 0x80070057) or "parameter is incorrect" in msgf.lower():
                                        # Unsupported format or bad parameter for this device; try next format
                                        last_param_exc = fe
                                        continue
                                    else:
                                        # Other errors bubble to outer handler
                                        raise
                            if image is None and last_param_exc is not None:
                                # Exhausted candidates; raise last param error for outer handling
                                raise last_param_exc
                        except Exception as he:
                            msg = str(he) or ""
                            # Detect by HRESULT when available (WIA_ERROR_PAPER_EMPTY = 0x80210003)
                            try:
                                hresult = getattr(he, "hresult", None)
                            except Exception:
                                hresult = None
                            lowercase = msg.lower()
                            if (
                                hresult in (-2145320957, 0x80210003)
                                or "wia_error_paper_empty" in lowercase
                                or "there are no pages to scan" in lowercase
                                or ("feeder" in lowercase and "empty" in lowercase)
                                or "no documents left in the document feeder" in lowercase
                                or ("user requested a scan" in lowercase and "no documents" in lowercase and "feeder" in lowercase)
                                or "no documents" in lowercase
                            ):
                                break
                            else:
                                raise
                        if image is None:
                            break
                        img_path = os.path.join(temp_dir, f"{base}_p{page_index:03d}.jpg")
                        try:
                            image.SaveFile(img_path)
                        except Exception as e:
                            if page_index == 1:
                                raise Exception(f"Failed to save scanned image: {e}")
                            break
                        try:
                            cropped_path = self._auto_crop_margins(img_path)
                            use_img_path = cropped_path or img_path
                        except Exception:
                            use_img_path = img_path
                        pdf_path = self._image_to_pdf(use_img_path)
                        out_path = pdf_path if pdf_path else use_img_path
                        outputs.append(out_path)
                        page_index += 1
                except Exception as e:
                    raise Exception(str(e))

            # Emit all collected outputs
            if not outputs:
                self.error.emit("Scan canceled or no image acquired.")
                return
            self.success.emit(outputs)
        except Exception as e:
            self.error.emit(str(e))
        finally:
            try:
                import pythoncom
                pythoncom.CoUninitialize()
            except Exception:
                pass
            self.finished.emit()

    def _auto_crop_margins(self, img_path: str) -> str | None:
        """Detect and crop margins (scanner platen/gray borders) from an image using adaptive background analysis
        plus projection-based edge refinement. Returns path to a new cropped JPG if cropping occurred; otherwise None.
        The original file remains untouched.
        """
        try:
            import warnings
            from statistics import median, pstdev
            from PIL import Image, ImageFilter
            # Suppress decompression bomb warnings for controlled local scans
            try:
                warnings.simplefilter("ignore", Image.DecompressionBombWarning)
                Image.MAX_IMAGE_PIXELS = None
            except Exception:
                pass

            with Image.open(img_path) as im:
                gray = im.convert("L")
                w, h = gray.size

                # 1) Estimate background from outer border samples
                bw = max(1, min(50, int(w * 0.05)))
                bh = max(1, min(50, int(h * 0.05)))
                border_samples = []
                border_samples.extend(list(gray.crop((0, 0, w, bh)).getdata()))          # top
                border_samples.extend(list(gray.crop((0, h - bh, w, h)).getdata()))      # bottom
                border_samples.extend(list(gray.crop((0, 0, bw, h)).getdata()))          # left
                border_samples.extend(list(gray.crop((w - bw, 0, w, h)).getdata()))      # right
                if not border_samples:
                    return None
                bg_med = int(median(border_samples))
                try:
                    bg_std = max(1.0, float(pstdev(border_samples)))
                except Exception:
                    bg_std = 8.0
                delta = max(8.0, 2.0 * bg_std)  # sensitivity relative to noise

                # 2) Build content mask (content = pixels that differ enough from background)
                diff = gray.point(lambda p, m=bg_med: abs(p - m))
                diff = diff.filter(ImageFilter.MedianFilter(size=3))
                mask = diff.point(lambda d, th=delta: 255 if d >= th else 0).convert("L")  # grayscale 0..255
                # Slight dilation to connect faint edges
                mask = mask.filter(ImageFilter.MaxFilter(3))

                # Initial bbox
                bbox = mask.getbbox()
                if not bbox:
                    # Fallback simple threshold for very clean scans
                    simple = gray.point(lambda p: 255 if p < 240 else 0, mode="L")
                    bbox = simple.getbbox()
                    if not bbox:
                        return None

                left, top, right, bottom = bbox

                # 3) Projection-based refinement to tighten edges and remove residual gray
                # Compute row/column sums within a working view for speed by downscaling the mask
                # but map refined bounds back to original coordinates.
                max_side = 1600  # limit analysis size for speed
                scale = 1.0
                m = mask
                mw, mh = m.size
                if max(mw, mh) > max_side:
                    scale = max_side / float(max(mw, mh))
                    new_w = max(1, int(mw * scale))
                    new_h = max(1, int(mh * scale))
                    m_small = m.resize((new_w, new_h), Image.NEAREST)
                else:
                    m_small = m
                sw, sh = m_small.size

                # Map bbox to small space
                s_left = int(left * scale)
                s_top = int(top * scale)
                s_right = int(right * scale)
                s_bottom = int(bottom * scale)

                ms = m_small.load()
                # Density thresholds: require at least 0.5% of pixels set on a scanline/column to consider content
                row_thresh = max(1, int((s_right - s_left) * 0.005))
                col_thresh = max(1, int((s_bottom - s_top) * 0.005))
                # Limits: do not trim more than 25% from each side
                max_trim_x = int((s_right - s_left) * 0.25)
                max_trim_y = int((s_bottom - s_top) * 0.25)

                # Trim from top
                trim = 0
                for y in range(s_top, s_bottom):
                    count = 0
                    for x in range(s_left, s_right):
                        if ms[x, y] >= 128:
                            count += 1
                            if count >= row_thresh:
                                break
                    if count < row_thresh and trim < max_trim_y:
                        trim += 1
                    else:
                        break
                s_top += trim

                # Trim from bottom
                trim = 0
                for y in range(s_bottom - 1, s_top - 1, -1):
                    count = 0
                    for x in range(s_left, s_right):
                        if ms[x, y] >= 128:
                            count += 1
                            if count >= row_thresh:
                                break
                    if count < row_thresh and trim < max_trim_y:
                        trim += 1
                    else:
                        break
                s_bottom -= trim

                # Trim from left
                trim = 0
                for x in range(s_left, s_right):
                    count = 0
                    for y in range(s_top, s_bottom):
                        if ms[x, y] >= 128:
                            count += 1
                            if count >= col_thresh:
                                break
                    if count < col_thresh and trim < max_trim_x:
                        trim += 1
                    else:
                        break
                s_left += trim

                # Trim from right
                trim = 0
                for x in range(s_right - 1, s_left - 1, -1):
                    count = 0
                    for y in range(s_top, s_bottom):
                        if ms[x, y] >= 128:
                            count += 1
                            if count >= col_thresh:
                                break
                    if count < col_thresh and trim < max_trim_x:
                        trim += 1
                    else:
                        break
                s_right -= trim

                # Map back to original coordinates
                if scale != 1.0:
                    left = int(s_left / scale)
                    top = int(s_top / scale)
                    right = int(s_right / scale)
                    bottom = int(s_bottom / scale)
                else:
                    left, top, right, bottom = s_left, s_top, s_right, s_bottom

                # Safety padding (tight but inside bounds)
                pad = 2
                left = max(0, left + 0 - pad)
                top = max(0, top + 0 - pad)
                right = min(w, right + pad)
                bottom = min(h, bottom + pad)

                # Avoid over-cropping if essentially full image
                if (right - left) >= w * 0.997 and (bottom - top) >= h * 0.997:
                    return None

                if right - left < 5 or bottom - top < 5:
                    return None

                cropped = im.crop((left, top, right, bottom))

            # Save cropped as new temp JPG
            fd, out_path = tempfile.mkstemp(suffix="_cropped.jpg")
            os.close(fd)
            try:
                with cropped:
                    cropped.save(out_path, "JPEG", quality=95, optimize=True)
            except Exception:
                try:
                    if os.path.exists(out_path):
                        os.remove(out_path)
                except Exception:
                    pass
                return None
            return out_path
        except Exception:
            return None
