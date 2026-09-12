"""Transport/storage acceptance bounds, not subscription or privacy policy."""
MAX_SCREENSHOT_BYTES = 6 * 1024 * 1024
MAX_SCREENSHOT_DIMENSION = 16384


def validate_screenshot(metadata, image):
    if not isinstance(image, bytes) or not 0 < len(image) <= MAX_SCREENSHOT_BYTES:
        raise ValueError('Screenshot exceeds supported byte limit')
    if metadata.get('mime_type') not in ('image/jpeg', 'image/png'):
        raise ValueError('Unsupported screenshot type')
    for name in ('width', 'height'):
        value = metadata.get(name)
        if isinstance(value, bool) or not isinstance(value, int) or not 0 < value <= MAX_SCREENSHOT_DIMENSION:
            raise ValueError('Screenshot exceeds supported dimensions')
