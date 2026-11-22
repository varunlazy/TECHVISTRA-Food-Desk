package org.techvistra.fooddesk;

import android.content.Intent;
import android.graphics.Color;
import android.os.Bundle;
import android.util.Size;
import android.view.Gravity;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.TextView;
import androidx.activity.ComponentActivity;
import androidx.camera.core.CameraSelector;
import androidx.camera.core.ImageAnalysis;
import androidx.camera.core.ImageProxy;
import androidx.camera.core.Preview;
import androidx.camera.lifecycle.ProcessCameraProvider;
import androidx.camera.view.PreviewView;
import androidx.core.content.ContextCompat;
import com.google.common.util.concurrent.ListenableFuture;
import com.google.zxing.BarcodeFormat;
import com.google.zxing.BinaryBitmap;
import com.google.zxing.DecodeHintType;
import com.google.zxing.MultiFormatReader;
import com.google.zxing.PlanarYUVLuminanceSource;
import com.google.zxing.common.HybridBinarizer;
import java.nio.ByteBuffer;
import java.util.Collections;
import java.util.EnumMap;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;

public class ScannerActivity extends ComponentActivity {
    private ExecutorService cameraExecutor;
    private ProcessCameraProvider provider;
    private PreviewView previewView;
    private final AtomicBoolean done = new AtomicBoolean(false);

    private int dp(int p) {return (int)(p*getResources().getDisplayMetrics().density+0.5f);}

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        cameraExecutor = Executors.newSingleThreadExecutor();
        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(Color.BLACK);
        previewView = new PreviewView(this);
        previewView.setImplementationMode(PreviewView.ImplementationMode.COMPATIBLE);
        root.addView(previewView,new FrameLayout.LayoutParams(-1,-1));
        Button close = new Button(this);
        close.setText("✕  CLOSE");
        FrameLayout.LayoutParams top = new FrameLayout.LayoutParams(dp(145),dp(52),Gravity.TOP|Gravity.START);
        top.topMargin=dp(32);top.leftMargin=dp(16);
        root.addView(close,top);
        close.setOnClickListener(v -> finish());
        TextView prompt = new TextView(this);
        prompt.setText("SCAN STUDENT FOOD PASS\nHold QR inside the camera frame");
        prompt.setTextSize(18);
        prompt.setTextColor(Color.WHITE);
        prompt.setGravity(Gravity.CENTER);
        prompt.setBackgroundColor(Color.argb(170,10,14,27));
        FrameLayout.LayoutParams bottom = new FrameLayout.LayoutParams(-1,dp(100),Gravity.BOTTOM);
        bottom.leftMargin=dp(12);bottom.rightMargin=dp(12);bottom.bottomMargin=dp(28);
        root.addView(prompt,bottom);
        setContentView(root);
        startCamera();
    }

    private void startCamera() {
        ListenableFuture<ProcessCameraProvider> future = ProcessCameraProvider.getInstance(this);
        future.addListener(() -> {
            try {
                provider = future.get();
                provider.unbindAll();
                Preview preview = new Preview.Builder().build();
                preview.setSurfaceProvider(previewView.getSurfaceProvider());
                ImageAnalysis analyzer = new ImageAnalysis.Builder()
                    .setTargetResolution(new Size(1280,720))
                    .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                    .build();
                analyzer.setAnalyzer(cameraExecutor,this::decodeImage);
                provider.bindToLifecycle(this,CameraSelector.DEFAULT_BACK_CAMERA,preview,analyzer);
            } catch(Exception e) {
                runOnUiThread(() -> android.widget.Toast.makeText(this,
                    "Camera setup error: "+e.getMessage(),android.widget.Toast.LENGTH_LONG).show());
            }
        },ContextCompat.getMainExecutor(this));
    }

    private void decodeImage(ImageProxy image) {
        try {
            if(done.get()) return;
            ImageProxy.PlaneProxy y=image.getPlanes()[0];
            int w=image.getWidth(),h=image.getHeight();
            byte[] luminance=new byte[w*h];
            ByteBuffer buffer=y.getBuffer();
            int rowStride=y.getRowStride(), pixelStride=y.getPixelStride();
            for(int row=0;row<h;row++) {
                for(int col=0;col<w;col++) luminance[row*w+col]=buffer.get(row*rowStride+col*pixelStride);
            }
            PlanarYUVLuminanceSource source=new PlanarYUVLuminanceSource(luminance,w,h,0,0,w,h,false);
            MultiFormatReader reader=new MultiFormatReader();
            Map<DecodeHintType,Object> hints=new EnumMap<>(DecodeHintType.class);
            hints.put(DecodeHintType.POSSIBLE_FORMATS,Collections.singletonList(BarcodeFormat.QR_CODE));
            hints.put(DecodeHintType.TRY_HARDER,Boolean.TRUE);
            reader.setHints(hints);
            String decoded=null;
            try {decoded=reader.decodeWithState(new BinaryBitmap(new HybridBinarizer(source))).getText();}
            catch(Exception first) {
                try {decoded=reader.decodeWithState(new BinaryBitmap(new HybridBinarizer(source.rotateCounterClockwise()))).getText();}
                catch(Exception ignored) { }
            }
            if(decoded!=null && !decoded.isEmpty() && done.compareAndSet(false,true)) {
                String result=decoded;
                runOnUiThread(() -> {
                    Intent data=new Intent().putExtra("qr",result);
                    setResult(RESULT_OK,data);
                    finish();
                });
            }
        } catch(Exception ignored) { }
        finally {image.close();}
    }

    @Override protected void onDestroy() {
        if(provider!=null)provider.unbindAll();
        if(cameraExecutor!=null)cameraExecutor.shutdown();
        super.onDestroy();
    }
}
