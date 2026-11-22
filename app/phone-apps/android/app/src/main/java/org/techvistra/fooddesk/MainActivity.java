package org.techvistra.fooddesk;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.view.WindowManager;
import android.webkit.JavascriptInterface;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.text.InputType;
import android.net.Uri;
import org.json.JSONObject;
import java.net.URI;

public class MainActivity extends Activity {
    private static final int SCAN_REQUEST = 41;
    private static final int CAMERA_REQUEST = 42;
    private String baseUrl = "";
    private WebView webView;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        showConnectionScreen();
    }

    private int dp(int value) {
        return (int)(getResources().getDisplayMetrics().density * value + 0.5f);
    }
    private TextView label(String value, int size) {
        TextView v = new TextView(this);
        v.setText(value); v.setTextSize(size); v.setTextColor(Color.rgb(28, 35, 63));
        return v;
    }
    private void showConnectionScreen() {
        if(webView != null) { webView.destroy(); webView = null; }
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(22),dp(55),dp(22),dp(22));
        root.setBackgroundColor(Color.rgb(247, 248, 254));
        TextView title = label("TECHVISTRA '26",27);
        root.addView(title);
        TextView desc = label("Offline live QR scanner • Phone camera • No HTTPS required",15);
        desc.setPadding(0,dp(8),0,dp(24)); root.addView(desc);
        TextView subtitle = label("Event laptop local IP",14); root.addView(subtitle);
        EditText host = new EditText(this);
        host.setSingleLine(true);
        host.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        host.setHint("192.168.1.50");
        host.setText(getPreferences(MODE_PRIVATE).getString("laptop", ""));
        root.addView(host);
        Button connect = new Button(this); connect.setText("CONNECT TO FOOD DESK");
        root.addView(connect);
        TextView info = label("Join the same PRIVATE Wi-Fi as the event laptop. Use the laptop IP, never localhost. Default port: 8787. The login and redemption records stay on the laptop.",13);
        info.setPadding(0,dp(22),0,0); root.addView(info);
        TextView error = label("",13); error.setTextColor(Color.RED); root.addView(error);
        connect.setOnClickListener(v -> {
            String value = host.getText().toString().trim();
            String next = normalizeLocalAddress(value);
            if(next == null) { error.setText("Enter a valid private LAN IP, e.g. 192.168.1.50"); return; }
            baseUrl = next;
            getPreferences(MODE_PRIVATE).edit().putString("laptop",baseUrl).apply();
            showDesk();
        });
        setContentView(root);
    }

    private String normalizeLocalAddress(String raw) {
        try {
            String value = raw.matches("(?i)^https?://.*") ? raw : "http://"+raw;
            URI uri = new URI(value);
            if(!"http".equals(uri.getScheme()) && !"https".equals(uri.getScheme())) return null;
            if(uri.getRawUserInfo()!=null || uri.getRawQuery()!=null || uri.getRawFragment()!=null) return null;
            if(uri.getRawPath()!=null && !uri.getRawPath().isEmpty() && !"/".equals(uri.getRawPath())) return null;
            String ip = uri.getHost();
            if(ip==null || !ip.matches("[0-9.]+")) return null;
            String[] octets = ip.split("\\.");
            if(octets.length!=4) return null;
            int[] a = new int[4];
            for(int i=0;i<4;i++) {
                if(octets[i].isEmpty()) return null;
                a[i]=Integer.parseInt(octets[i]);
                if(a[i]<0 || a[i]>255) return null;
            }
            boolean privateLAN = a[0]==10 || (a[0]==172 && a[1]>=16 && a[1]<=31) ||
                                 (a[0]==192 && a[1]==168) || (a[0]==169 && a[1]==254);
            if(!privateLAN) return null;
            int port = uri.getPort()==-1 ? 8787 : uri.getPort();
            if(port<1 || port>65535) return null;
            return uri.getScheme()+"://"+ip+":"+port+"/";
        } catch(Exception ex) {return null;}
    }

    private void showDesk() {
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(Color.WHITE);
        LinearLayout bar = new LinearLayout(this);
        bar.setPadding(dp(12),dp(8),dp(12),dp(8));
        bar.setBackgroundColor(Color.rgb(240,241,250));
        TextView name = label(baseUrl,12);
        bar.addView(name, new LinearLayout.LayoutParams(0,dp(46),1));
        name.setGravity(Gravity.CENTER_VERTICAL);
        Button change = new Button(this); change.setText("Change");
        bar.addView(change); change.setOnClickListener(v -> showConnectionScreen());
        root.addView(bar);
        webView = new WebView(this);
        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        settings.setMediaPlaybackRequiresUserGesture(true);
        webView.setWebChromeClient(new WebChromeClient());
        webView.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri u=request.getUrl();
                return !(u.getScheme()+"://"+u.getHost()+":"+(u.getPort()==-1?8787:u.getPort())+"/").equals(baseUrl);
            }
            @Override public void onReceivedError(WebView view, WebResourceRequest req, android.webkit.WebResourceError error) {
                if(req.isForMainFrame()) runOnUiThread(() ->
                    android.widget.Toast.makeText(MainActivity.this,
                        "Cannot connect. Check Wi-Fi, laptop IP and server.",
                        android.widget.Toast.LENGTH_LONG).show());
            }
        });
        // Limited bridge: only opens the camera. Student verification stays in
        // the authenticated browser session and uses the existing server APIs.
        webView.addJavascriptInterface(new ScannerBridge(), "TechvistraAndroid");
        root.addView(webView, new LinearLayout.LayoutParams(-1,0,1));
        setContentView(root);
        webView.loadUrl(baseUrl);
    }

    private final class ScannerBridge {
        @JavascriptInterface public void openScanner() {
            runOnUiThread(() -> {
                if(checkSelfPermission(Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
                    requestPermissions(new String[]{Manifest.permission.CAMERA}, CAMERA_REQUEST);
                } else { openCamera(); }
            });
        }
    }

    private void openCamera() {
        startActivityForResult(new Intent(this, ScannerActivity.class), SCAN_REQUEST);
    }

    @Override public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] results) {
        super.onRequestPermissionsResult(requestCode, permissions, results);
        if(requestCode==CAMERA_REQUEST) {
            if(results.length>0 && results[0]==PackageManager.PERMISSION_GRANTED) openCamera();
            else android.widget.Toast.makeText(this,"Allow Camera permission in Settings",android.widget.Toast.LENGTH_LONG).show();
        }
    }

    @Override protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode,resultCode,data);
        if(requestCode!=SCAN_REQUEST || resultCode!=RESULT_OK || data==null || webView==null)return;
        String token = data.getStringExtra("qr");
        if(token==null || token.isEmpty())return;
        webView.evaluateJavascript("window.techvistraReceiveNativeQR("+JSONObject.quote(token)+");",null);
    }

    @Override public void onBackPressed() {
        if(webView!=null && webView.canGoBack()) webView.goBack();
        else if(webView!=null)showConnectionScreen();
        else super.onBackPressed();
    }

    @Override protected void onDestroy() {
        if(webView!=null) {webView.destroy();webView=null;}
        super.onDestroy();
    }
}
