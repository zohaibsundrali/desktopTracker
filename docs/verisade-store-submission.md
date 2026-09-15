# Verisade Microsoft Store submission candidate

The Store package uses the identity supplied from Partner Center:

- Name: `Verisade.Verisade`
- Publisher: `CN=07D5F1AC-884A-4074-94D6-C211985F5D32`
- Publisher display name and product display name: `Verisade`
- Version: app version with a final `.0` (currently `1.1.0.0`)
- Windows Desktop x64, Windows 10 build 19041 or later

Run **Windows desktop build** manually on the reviewed branch with signing disabled. Download the `verisade-store-<commit>` artifact. Check `package-report.json`: `configured` must be true. PR builds contain fixture configuration and must not be submitted. The package includes only the previously approved public backend configuration. No certificate, password, or service-role key is needed to build a Store submission package.

`Verisade.msix` is an unsigned **Partner Center submission candidate**, not a direct-install fix for Smart App Control. Upload it to the existing MSIX product's submission Packages section after the remaining review requirements are complete. Microsoft signs Store-distributed packages; passing MakeAppx does not mean the app passed Store certification or an installed-device test. Do not distribute the raw artifact to employees or ask them to disable Windows protection.

The Store payload has its own update-channel marker and directs users to Microsoft Store for updates. It never downloads the classic EXE updater. The existing classic installer build remains available separately. Package staging preserves the frozen app and its libraries; Windows MakeAppx validates the manifest, then the pipeline unpacks and compares the identity and all staged payload hashes. These are packaging checks, not runtime capture acceptance.

## Remaining submission work

1. Validate Store installation and launch on a fresh Windows 11 test device with Smart App Control enabled, through an appropriate Store testing distribution. Also test supported Windows 10 if advertised.
2. Test sign-in/device enrollment using a disposable active **employee** account, Start/Pause/Resume/Stop, screenshots and input aggregates, project selection, offline recovery, lock/sleep, uninstall/reinstall and updates. Capture data must appear in the correct organization. Owner and other tracking roles still require a separate login/authorization implementation; do not advertise them as accepted by this candidate.
3. The app needs the `runFullTrust` restricted capability because it is a Python Win32 desktop tracker with explicit screen/input/app capture, Windows session notifications and durable local queues. Provide this explanation honestly in certification notes and supply the reviewer a working test account through Partner Center's private reviewer fields.
4. Review monitoring consent, a real public privacy-policy URL, support details, age ratings, availability/pricing, screenshots and Store description. The generated V monogram is a basic package asset, not a completed marketing asset set. Existing in-app DevTrack labels remain; a complete Verisade UI rebrand is separate.
5. Existing Inno Setup startup tasks do not apply to MSIX. This candidate is manually launched; Store startup integration is not implemented.
6. The Store ID is still needed to connect an authenticated dashboard Install button to this exact listing. Name reservation is not Store approval. No listing has been published by this change.

Do not sign this Store candidate using a self-signed certificate and claim public trust. Do not treat an EXE/MSI listing as interchangeable with this MSIX product.

References: [manual desktop packaging](https://learn.microsoft.com/en-us/windows/msix/desktop/desktop-to-uwp-manual-conversion), [Store signing](https://learn.microsoft.com/en-us/windows/msix/package/sign-msix-package-guide).
