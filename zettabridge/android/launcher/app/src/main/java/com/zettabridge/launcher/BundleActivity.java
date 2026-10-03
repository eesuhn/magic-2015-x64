package com.zettabridge.launcher;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.graphics.Color;
import android.os.Bundle;
import android.util.Log;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;

/**
 * Home-screen entry of a single-game build. When this APK carries a bundled game it is installed
 * on first launch (BundledGame) and then started directly; later launches go straight to the
 * game. A build without a bundled game opens the ordinary library.
 *
 * Preparation runs once per process, whatever happens to the activity: a recreated or relaunched
 * instance attaches to the run in progress instead of starting a second import.
 */
public class BundleActivity extends Activity {
    private static final String TAG = "zb-bundle";

    // Process-wide preparation state, guarded by LOCK.
    private static final Object LOCK = new Object();
    private static Thread worker;
    private static BundleActivity shown;
    private static String lastMessage = "Setting up the game for the first time...";
    private static long lastDone;
    private static long lastTotal;

    private TextView status;
    private ProgressBar bar;
    private Button retry;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        if (!BundledGame.isBundled(this)) {
            startActivity(new Intent(this, LibraryActivity.class));
            finishAndRemoveTask();
            return;
        }
        boolean running;
        synchronized (LOCK) {
            running = worker != null;
        }
        String ready = running ? null : BundledGame.readyPackage(this);
        if (ready != null) {
            launch(ready);
            return;
        }
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        setContentView(buildUi());
        synchronized (LOCK) {
            shown = this;
            showProgress(lastMessage, lastDone, lastTotal);
        }
        start(getApplicationContext());
    }

    @Override
    protected void onDestroy() {
        synchronized (LOCK) {
            if (shown == this) shown = null;
        }
        super.onDestroy();
    }

    private View buildUi() {
        int pad = dp(32);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setGravity(Gravity.CENTER);
        root.setPadding(pad, pad, pad, pad);
        root.setBackgroundColor(Color.BLACK);

        status = new TextView(this);
        status.setTextColor(Color.WHITE);
        status.setTextSize(TypedValue.COMPLEX_UNIT_SP, 18);
        status.setGravity(Gravity.CENTER);
        root.addView(status);

        bar = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        bar.setMax(1000);
        bar.setIndeterminate(true);
        LinearLayout.LayoutParams barParams = new LinearLayout.LayoutParams(dp(360), LinearLayout.LayoutParams.WRAP_CONTENT);
        barParams.topMargin = dp(16);
        root.addView(bar, barParams);

        retry = new Button(this);
        retry.setText("Retry");
        retry.setVisibility(View.GONE);
        retry.setOnClickListener(v -> {
            retry.setVisibility(View.GONE);
            bar.setVisibility(View.VISIBLE);
            start(getApplicationContext());
        });
        LinearLayout.LayoutParams retryParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        retryParams.topMargin = dp(16);
        root.addView(retry, retryParams);
        return root;
    }

    /** Starts the process-wide preparation unless it is already running. */
    private static void start(Context app) {
        synchronized (LOCK) {
            if (worker != null) return;
            lastMessage = "Setting up the game for the first time...";
            lastDone = 0;
            lastTotal = 0;
            worker = new Thread(() -> run(app), "zb-bundle");
            worker.start();
        }
    }

    private static void run(Context app) {
        String pkg = null;
        String failure = null;
        try {
            pkg = BundledGame.prepare(app, (message, done, total) -> {
                BundleActivity target;
                synchronized (LOCK) {
                    lastMessage = message;
                    lastDone = done;
                    lastTotal = total;
                    target = shown;
                }
                if (target != null) target.runOnUiThread(() -> target.showProgress(message, done, total));
            });
        } catch (Exception e) {
            Log.e(TAG, "cannot prepare the bundled game", e);
            failure = e.getMessage() != null ? e.getMessage() : e.toString();
        }
        BundleActivity target;
        synchronized (LOCK) {
            worker = null;
            target = shown;
        }
        // Nobody watching (the user left): the next launch finds the game ready and starts it.
        if (target == null) return;
        final String done = pkg;
        final String error = failure;
        target.runOnUiThread(() -> {
            if (error != null) target.showFailure(error);
            else target.launch(done);
        });
    }

    private void showProgress(String message, long done, long total) {
        if (isFinishing() || isDestroyed() || status == null) return;
        if (total > 0) {
            bar.setIndeterminate(false);
            bar.setProgress((int) (done * 1000 / total));
            status.setText(String.format("%s %d%%", message, done * 100 / total));
        } else {
            bar.setIndeterminate(true);
            status.setText(message);
        }
    }

    private void showFailure(String message) {
        if (isFinishing() || isDestroyed() || status == null) return;
        bar.setVisibility(View.GONE);
        status.setText("Setup failed: " + message);
        retry.setVisibility(View.VISIBLE);
    }

    private void launch(String pkg) {
        if (isFinishing() || isDestroyed()) return;
        startActivity(PluginSwitchActivity.intent(this, pkg));
        // The game runs in its own (guest) task; leaving this one behind would show the app twice
        // in Recents.
        finishAndRemoveTask();
    }

    private int dp(int value) {
        return (int) TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, value, getResources().getDisplayMetrics());
    }
}
