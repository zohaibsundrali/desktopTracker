# Verisade desktop fonts

These static TrueType faces are derived from the exact self-hosted WOFF2 files in the website's `src/app/fonts/` directory: Inter 400/700 and Space Grotesk 500/700. The website uses Inter for controls and Space Grotesk for headings and its wordmark.

The WOFF2 sources are variable fonts. Conversion used fontTools `instantiateVariableFont(font, {'wght': weight})`, cleared the WOFF2 flavor, and normalized the family/style name and bold flags for native Windows GDI/Tk selection. No outlines were redesigned. The bundled SIL Open Font Licenses apply. Conversion tooling is not required at runtime.

PyInstaller includes these files under `assets/fonts`. `login_design.load_fonts` registers them privately for the application on Windows; users do not need to install fonts system-wide.
