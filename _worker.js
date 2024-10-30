export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    
    // Add CORS and security headers
    const headers = {
      'Cross-Origin-Opener-Policy': 'same-origin',
      'Cross-Origin-Embedder-Policy': 'require-corp'
    };

    // Serve static files from the bucket
    return env.ASSETS.fetch(request.url, {
      headers: headers
    });
  }
};
