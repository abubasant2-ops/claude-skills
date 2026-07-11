{{flutter_js}}
{{flutter_build_config}}

_flutter.loader.load({
  config: {
    // Serve CanvasKit from the app's own bundle instead of gstatic CDN so the
    // web build works offline and behind restricted networks (blueprint NFR-02).
    canvasKitBaseUrl: 'canvaskit/',
  },
});
