package com.zettabridge.launcher;

import android.app.Activity;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.view.KeyEvent;
import android.view.Window;

import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;

/**
 * Gives a guest's Back press a real duration.
 *
 * Under gesture navigation the framework turns a back swipe into KEYCODE_BACK down and up
 * synthesized in the same instant (ViewRootImpl's compat back callback). Games that keep Back as
 * a button state and sample it once per frame, as Magic 2015 does from onKeyDown/onKeyUp, see it
 * pressed and released between two frames and never act on it. A hardware or injected Back key
 * arrives with ~100 ms between down and up, and works.
 *
 * So a Back release that follows its press by less than {@link #MIN_PRESS_MS} is held back until
 * the press has lasted that long. Every other key, and every Back press that already lasts long
 * enough, goes through untouched.
 */
final class GuestBackKeys {
    static final long MIN_PRESS_MS = 100;

    private GuestBackKeys() {}

    static void install(Activity activity) {
        Window window = activity.getWindow();
        if (window == null) return;
        final Window.Callback original = window.getCallback();
        if (original == null || Proxy.isProxyClass(original.getClass())) return;
        final Handler main = new Handler(Looper.getMainLooper());
        final long[] downAt = {0};
        final KeyEvent[] pendingUp = {null};
        final Runnable releaseUp = () -> {
            KeyEvent up = pendingUp[0];
            pendingUp[0] = null;
            if (up != null) original.dispatchKeyEvent(up);
        };
        window.setCallback((Window.Callback) Proxy.newProxyInstance(
                Window.Callback.class.getClassLoader(), new Class<?>[] {Window.Callback.class},
                (proxy, method, args) -> {
                    if ("dispatchKeyEvent".equals(method.getName()) && args != null && args.length == 1
                            && args[0] instanceof KeyEvent) {
                        KeyEvent event = (KeyEvent) args[0];
                        if (event.getKeyCode() == KeyEvent.KEYCODE_BACK) {
                            if (event.getAction() == KeyEvent.ACTION_DOWN) {
                                // A new press first ends one whose release is still held back.
                                if (pendingUp[0] != null) {
                                    main.removeCallbacks(releaseUp);
                                    releaseUp.run();
                                }
                                downAt[0] = SystemClock.uptimeMillis();
                            } else if (event.getAction() == KeyEvent.ACTION_UP) {
                                long held = SystemClock.uptimeMillis() - downAt[0];
                                if (held < MIN_PRESS_MS) {
                                    pendingUp[0] = new KeyEvent(event);
                                    main.postDelayed(releaseUp, MIN_PRESS_MS - held);
                                    return true;
                                }
                            }
                        }
                    }
                    try {
                        return method.invoke(original, args);
                    } catch (InvocationTargetException e) {
                        throw e.getCause();
                    }
                }));
    }
}
