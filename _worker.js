export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    
    // Add CORS and security headers
    const headers = {
      'Cross-Origin-Opener-Policy': 'same-origin',
      'Cross-Origin-Embedder-Policy': 'require-corp',
      'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
      'X-Content-Type-Options': 'nosniff',
      'X-Frame-Options': 'DENY',
      'Content-Security-Policy': "default-src 'self' unpkg.com; script-src 'self' 'unsafe-eval' 'unsafe-inline' unpkg.com; worker-src 'self' blob:; style-src 'self' 'unsafe-inline';"
    };

    // Serve static files from the bucket
    return env.ASSETS.fetch(request.url, {
      headers: headers
    });
  }
};
