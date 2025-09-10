import os
import tempfile
import random
import pyinsane2

from PIL import Image
from PyQt5.QtCore import QObject, pyqtSignal
from core.config_loader import device_config

_PYINSANE_READY = False

class ScanWorker(QObject):
    finished = pyqtSignal()
    success = pyqtSignal(list)
    error = pyqtSignal(str)


    def __init__(self, session_number, parent=None):
        super().__init__(parent)
        self.session_number = session_number

    def _image_to_pdf(self, img_path: str) -> str | None:
        """
        Convert a scanned image to a *small* one-page PDF.
        Strategy:
          1) Convert to 1-bit bilevel and write CCITT Group 4 TIFF.
          2) Wrap TIFF into a PDF (prefer img2pdf; fallback to ReportLab).
          3) As last resort, write a compressed JPEG-in-PDF.
        Returns output PDF path or None.
        """
        import os
        from PIL import Image

        base, _ = os.path.splitext(img_path)
        out_pdf = base + ".pdf"
        tiff_g4 = None
        jpg_small = None

        # Determine DPI hint (scan code sets 300; keep consistent if available)
        dpi_hint = 300

        # 1) Build CCITT Group 4 TIFF (bilevel) with dithering for smoother grays
        try:
            im = Image.open(img_path)

            # Normalize to grayscale first
            if im.mode != 'L':
                im = im.convert('L')

            # Floyd–Steinberg dithering -> 1-bit (visually softer than hard threshold)
            im = im.convert('1', dither=Image.FLOYDSTEINBERG)

            # Save as CCITT Group 4 TIFF (fax-grade)
            tiff_g4 = base + "_g4.tiff"
            im.save(tiff_g4, format="TIFF", compression="group4", dpi=(dpi_hint, dpi_hint))
        except Exception:
            tiff_g4 = None

        # 2) Wrap TIFF into a PDF
        if tiff_g4 and os.path.exists(tiff_g4):
            # 2a) Preferred: img2pdf (preserves CCITT and keeps files tiny)
            try:
                import img2pdf
                with open(tiff_g4, "rb") as tf, open(out_pdf, "wb") as pf:
                    pf.write(img2pdf.convert(tf, dpi=dpi_hint))
                # cleanup
                try:
                    os.remove(tiff_g4)
                except Exception:
                    pass
                return out_pdf
            except Exception:
                pass

            # 2b) Fallback: ReportLab wrapper
            try:
                from reportlab.pdfgen import canvas
                from reportlab.lib.pagesizes import letter
                from reportlab.lib.utils import ImageReader

                c = canvas.Canvas(out_pdf, pagesize=letter)
                page_w, page_h = letter
                img = ImageReader(tiff_g4)
                iw, ih = img.getSize()

                # Fit within 0.5" margins, keep aspect
                margin = 36  # points
                avail_w = page_w - 2 * margin
                avail_h = page_h - 2 * margin
                scale = min(avail_w / iw, avail_h / ih)
                dw, dh = iw * scale, ih * scale
                x, y = (page_w - dw) / 2, (page_h - dh) / 2

                c.drawImage(img, x, y, dw, dh, mask='auto')
                c.showPage()
                c.save()

                try:
                    os.remove(tiff_g4)
                except Exception:
                    pass
                return out_pdf
            except Exception:
                # keep trying below
                pass

        # 3) Last resort: compressed JPEG-in-PDF (still small enough)
        try:
            im = Image.open(img_path)
            if im.mode not in ('L', 'RGB'):
                im = im.convert('L')

            jpg_small = base + "_q40.jpg"
            im.save(jpg_small, format='JPEG', quality=40, optimize=True, subsampling=2)

            # Write into PDF with ReportLab
            from reportlab.pdfgen import canvas
            from reportlab.lib.pagesizes import letter
            from reportlab.lib.utils import ImageReader

            c = canvas.Canvas(out_pdf, pagesize=letter)
            page_w, page_h = letter
            img = ImageReader(jpg_small)
            iw, ih = img.getSize()
            margin = 36
            avail_w = page_w - 2 * margin
            avail_h = page_h - 2 * margin
            scale = min(avail_w / iw, avail_h / ih)
            dw, dh = iw * scale, ih * scale
            x, y = (page_w - dw) / 2, (page_h - dh) / 2
            c.drawImage(img, x, y, dw, dh)
            c.showPage()
            c.save()

            try:
                os.remove(jpg_small)
            except Exception:
                pass

            return out_pdf
        except Exception:
            # Final fallback: Pillow's native PDF writer (bigger files)
            try:
                im = Image.open(img_path)
                if im.mode not in ("RGB", "L"):
                    im = im.convert("RGB")
                im.save(out_pdf, "PDF", resolution=dpi_hint)
                return out_pdf
            except Exception:
                return None

    def run(self):
        try:
            # Initialize pyinsane once per process
            global _PYINSANE_READY
            if not _PYINSANE_READY:
                pyinsane2.init()
                _PYINSANE_READY = True

            devices = pyinsane2.get_devices()
            if not devices:
                self.error.emit("No scanner detected.")
                return

            saved_name = device_config.get("Scanner", "preferred_name", "")
            scanner = next((s for s in devices if s.name == saved_name), None)
            if scanner is None:
                scanner = devices[0]
                try:
                    device_config.set("Scanner", "preferred_name", scanner.name)
                    device_config.save()
                except Exception:
                    pass

            def set_opt(opt, value):
                try:
                    if opt in scanner.options:
                        scanner.options[opt].value = value
                except Exception:
                    pass

            # Safe defaults
            set_opt('resolution', 300)
            # Prefer true 1-bit B/W if the device supports it; else Gray
            try:
                if 'mode' in scanner.options:
                    modes = scanner.options['mode'].constraint
                    pick = next(
                        (m for m in ['Lineart', 'Black & White', 'BW', 'Binary', 'Mono', 'Gray', 'Grayscale', 'Color']
                         if m in modes), None)
                    if pick:
                        scanner.options['mode'].value = pick
                    else:
                        set_opt('mode', 'Gray')
            except Exception:
                set_opt('mode', 'Gray')

            # Source selection
            source_val = None
            if 'source' in scanner.options:
                try:
                    candidates = scanner.options['source'].constraint
                    source_val = next((s for s in ['ADF Duplex', 'ADF', 'FlatBed'] if s in candidates), candidates[0])
                    scanner.options['source'].value = source_val
                except Exception:
                    source_val = None

            # Geometry: full width, Letter height at current DPI
            try:
                dpi = scanner.options['resolution'].value if 'resolution' in scanner.options else 300
            except Exception:
                dpi = 300
            if all(o in scanner.options for o in ['tl-x', 'tl-y', 'br-x', 'br-y']):
                try:
                    set_opt('tl-x', scanner.options['tl-x'].constraint[0])
                    set_opt('tl-y', scanner.options['tl-y'].constraint[0])
                    set_opt('br-x', scanner.options['br-x'].constraint[1])
                    set_opt('br-y', int(11 * dpi))
                except Exception:
                    pass

            outputs = []
            base = f"scan_{self.session_number}_{random.randint(1000, 9999)}"
            page_idx = 1
            max_passes = 1 if (source_val == 'FlatBed') else 200  # hard guard

            for _ in range(max_passes):
                # Start single-page session
                try:
                    session = scanner.scan(multiple=False)
                except Exception as e:
                    msg = str(e) or "Scan start failed"
                    if "0x8021000A" in msg or "PAPER" in msg.upper():
                        break  # feeder empty
                    self.error.emit(f"Scanning error: {msg}")
                    return

                # Drain session
                try:
                    while True:
                        session.scan.read()
                except EOFError:
                    pass
                except StopIteration:
                    # Some WIA drivers raise StopIteration on feeder empty
                    try:
                        session.images.clear()
                    except Exception:
                        pass
                    break
                except Exception as e:
                    msg = str(e) or "Read failed"
                    if "0x8021000A" in msg or "PAPER" in msg.upper():
                        try:
                            session.images.clear()
                        except Exception:
                            pass
                        break
                    try:
                        session.images.clear()
                    except Exception:
                        pass
                    self.error.emit(f"Scanning error: {msg}")
                    return

                # Validate exactly one image
                try:
                    images = [img for img in getattr(session, "images", []) if hasattr(img, "save")]
                except Exception:
                    images = []

                if not images:
                    # No page produced this pass
                    break

                image = images[0]
                try:
                    jpg_path = os.path.join(tempfile.gettempdir(), f"{base}_p{page_idx:03d}.jpg")
                    image.save(jpg_path, "JPEG")
                    pdf_path = self._image_to_pdf(jpg_path)
                    if pdf_path:
                        outputs.append(pdf_path)
                        try:
                            os.remove(jpg_path)
                        except Exception:
                            pass
                    else:
                        outputs.append(jpg_path)
                    page_idx += 1
                except Exception as e:
                    try:
                        if 'jpg_path' in locals() and os.path.exists(jpg_path):
                            os.remove(jpg_path)
                    except Exception:
                        pass
                    try:
                        session.images.clear()
                    except Exception:
                        pass
                    self.error.emit(f"Failed to save scanned image: {e}")
                    return
                finally:
                    try:
                        session.images.clear()
                    except Exception:
                        pass

                # Flatbed: only one pass
                if source_val == 'FlatBed':
                    break

            if not outputs:
                self.error.emit("No pages scanned.")
                return

            print(f"[ScanWorker] Emitting {len(outputs)} files")
            self.success.emit(outputs)
            return  # IMPORTANT: return immediately; do not tear down backend here

        except pyinsane2.PyinsaneException as e:
            self.error.emit(f"Scanning failed: {e}")
        except Exception as e:
            self.error.emit(f"Unhandled scan error: {e}")
        finally:
            # Do NOT call pyinsane2.exit() here; leave backend initialized for process lifetime.
            self.finished.emit()