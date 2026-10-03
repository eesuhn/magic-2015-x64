package com.zettabridge.launcher;

import android.content.Context;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.content.res.AssetFileDescriptor;
import android.database.sqlite.SQLiteDatabase;
import android.util.Log;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.io.RandomAccessFile;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;
import java.util.zip.ZipInputStream;

import com.zettabridge.core.ZBridge;

/**
 * The game this APK ships with: assets/bundle/game.apk, plus its expansion files under
 * assets/bundle/obb/, all stored uncompressed (magic2015-port/tools.py), the OBB page-aligned.
 *
 * The expansion files are never copied. The game's Java side only checks that its OBB exists with
 * the right size, so a sparse placeholder of that size (no data blocks) stands at the path it
 * expects; its native side reads the OBB, and in the :guest process that path is a file window
 * (ZBridge.addFileWindow) onto the OBB's bytes inside this installed APK. Disk use is the APK.
 *
 * The OBB path is the one the game derives from the host package: main.VERSION.HOST_PACKAGE.obb
 * in the host's OBB directory. First launch imports the game as a plugin and creates the
 * placeholders; an app update re-imports the game, keeping its saved data.
 */
final class BundledGame {
    private static final String TAG = "zb-bundle";
    static final String GAME_ASSET = "bundle/game.apk";
    private static final String OBB_ASSET_DIR = "bundle/obb";
    private static final String STAMP_FILE = "bundle-stamp";
    private static final String PACKAGE_FILE = "bundle-package";
    // Identity prefix of a placeholder; earlier builds recorded full copies without it.
    private static final String PLACEHOLDER = "window:";
    // The game APK's unlock snapshot (see seedUnlocks) and the marker that it has been applied.
    private static final String UNLOCK_ASSET = "assets/opera-fan";
    private static final String UNLOCK_MARKER = "bundle-unlocks-v1";

    interface Progress {
        void update(String message, long done, long total);
    }

    private BundledGame() {}

    static boolean isBundled(Context c) {
        try (InputStream ignored = c.getAssets().open(GAME_ASSET)) {
            return true;
        } catch (IOException e) {
            return false;
        }
    }

    /** The imported game's package, when the plugin and every OBB placeholder are in place. */
    static String readyPackage(Context c) {
        String pkg = read(new File(c.getFilesDir(), PACKAGE_FILE));
        if (pkg == null || !stamp(c).equals(read(new File(c.getFilesDir(), STAMP_FILE)))) return null;
        PluginRecord r = PluginStore.find(c, pkg);
        if (r == null || !r.isLaunchable()) return null;
        if (!new File(c.getFilesDir(), UNLOCK_MARKER).exists()) return null;
        try {
            for (String name : obbAssets(c)) {
                if (!placeholderReady(c, name)) return null;
            }
        } catch (IOException e) {
            return null;
        }
        return pkg;
    }

    /** Imports the game and lays down its OBB placeholders as needed. Returns the game's package. */
    static String prepare(Context c, Progress progress) throws IOException {
        String stamp = stamp(c);
        File stampFile = new File(c.getFilesDir(), STAMP_FILE);
        File packageFile = new File(c.getFilesDir(), PACKAGE_FILE);
        String pkg = read(packageFile);
        PluginRecord existing = pkg != null ? PluginStore.find(c, pkg) : null;
        if (existing == null || !stamp.equals(read(stampFile))) {
            progress.update("Installing the game...", 0, 0);
            PluginRecord r;
            try (InputStream in = c.getAssets().open(GAME_ASSET)) {
                r = PluginStore.importApk(c, in);
            }
            if (!r.isLaunchable()) throw new IOException(r.label + ": " + r.status());
            pkg = r.packageName;
            write(packageFile, pkg);
        }
        for (String name : obbAssets(c)) writePlaceholder(c, name);
        PluginRecord r = PluginStore.find(c, pkg);
        if (r == null) throw new IOException("the imported game is missing");
        seedUnlocks(c, r);
        write(stampFile, stamp);
        return pkg;
    }

    /**
     * The bundled game is an androeed.ru repack whose unlock is a data snapshot, assets/opera-fan
     * (a zip of databases/purchase.db, files/p1.profile, shared_prefs/DuelsLoader.xml), which its
     * DuelsLoader.SmartDataRestoreForYou unzips into /data/data/<getPackageName()>/. Under
     * ZettaBridge that is the host's data directory, not the plugin's, so the game never sees it
     * and the purchases (all chapters, the expansion, every collection) stay locked.
     *
     * So it is applied here, to the plugin's own data directory: purchase.db is merged into the
     * game's database (which the game may already have created empty), files are added only when
     * missing so a player's progress is never overwritten, and the preferences, an empty Facebook
     * user name, are skipped. Runs once per install; a failure is logged and the game still runs.
     */
    private static void seedUnlocks(Context c, PluginRecord r) {
        File marker = new File(c.getFilesDir(), UNLOCK_MARKER);
        if (marker.exists()) return;
        File data = r.dataDir();
        try (ZipFile apk = new ZipFile(r.apk())) {
            ZipEntry snapshot = apk.getEntry(UNLOCK_ASSET);
            if (snapshot != null) {
                try (ZipInputStream zip = new ZipInputStream(apk.getInputStream(snapshot))) {
                    for (ZipEntry e; (e = zip.getNextEntry()) != null; ) {
                        String name = e.getName();
                        if (e.isDirectory() || name.contains("..") || name.startsWith("shared_prefs/")) continue;
                        File target = new File(data, name);
                        if (name.equals("databases/purchase.db") && target.exists()) {
                            File incoming = new File(c.getCacheDir(), "unlock-purchase.db");
                            copy(zip, incoming);
                            mergePurchases(target, incoming);
                            incoming.delete();
                        } else if (!target.exists()) {
                            File dir = target.getParentFile();
                            if (dir != null && !dir.isDirectory() && !dir.mkdirs()) throw new IOException("cannot create " + dir);
                            copy(zip, target);
                        }
                    }
                }
                Log.i(TAG, "unlock snapshot applied to " + data);
            }
            write(marker, "1");
        } catch (IOException | RuntimeException e) {
            Log.e(TAG, "cannot apply the unlock snapshot", e);
        }
    }

    /** Adds the snapshot's purchase records to the game's own purchase database. */
    private static void mergePurchases(File target, File incoming) {
        SQLiteDatabase db = SQLiteDatabase.openDatabase(target.getPath(), null, SQLiteDatabase.OPEN_READWRITE);
        try {
            db.execSQL("ATTACH DATABASE ? AS snap", new Object[] {incoming.getPath()});
            db.beginTransaction();
            try {
                db.execSQL("INSERT OR REPLACE INTO purchased SELECT * FROM snap.purchased");
                db.execSQL("INSERT OR IGNORE INTO history SELECT * FROM snap.history");
                db.setTransactionSuccessful();
            } finally {
                db.endTransaction();
            }
            db.execSQL("DETACH DATABASE snap");
        } finally {
            db.close();
        }
    }

    private static void copy(InputStream in, File out) throws IOException {
        try (OutputStream o = new FileOutputStream(out)) {
            byte[] buf = new byte[1 << 16];
            for (int n; (n = in.read(buf)) > 0; ) o.write(buf, 0, n);
        }
    }

    /**
     * In the :guest process, before plugin code runs: maps each OBB path onto its entry in this
     * APK. Failures are logged; the game then reads the placeholder and reports missing data.
     */
    static void registerFileWindows(Context c) {
        try {
            for (String name : obbAssets(c)) {
                try (AssetFileDescriptor afd = c.getAssets().openFd(OBB_ASSET_DIR + "/" + name)) {
                    File target = obbTarget(c, name);
                    String apk = c.getPackageCodePath();
                    ZBridge.addFileWindow(target.getPath(), apk, afd.getStartOffset(), afd.getLength());
                    String canonical = target.getCanonicalPath();
                    if (!canonical.equals(target.getPath())) {
                        ZBridge.addFileWindow(canonical, apk, afd.getStartOffset(), afd.getLength());
                    }
                }
            }
        } catch (IOException | RuntimeException e) {
            Log.e(TAG, "cannot map the bundled OBB", e);
        }
    }

    /** A sparse file of the OBB's size: what the game's existence and size checks look at. */
    private static void writePlaceholder(Context c, String name) throws IOException {
        if (placeholderReady(c, name)) return;
        File target = obbTarget(c, name);
        File dir = target.getParentFile();
        if (dir == null || (!dir.isDirectory() && !dir.mkdirs())) throw new IOException("cannot create " + dir);
        // Replaces a full copy from an earlier build, which frees its space.
        if (target.exists() && !target.delete()) throw new IOException("cannot replace " + target);
        long length = assetLength(c, OBB_ASSET_DIR + "/" + name);
        try (RandomAccessFile file = new RandomAccessFile(target, "rw")) {
            file.setLength(length);  // extends without writing: no data blocks are allocated
        }
        if (target.length() != length) throw new IOException("cannot size " + target);
        write(identityFile(c, name), PLACEHOLDER + assetIdentity(c, name));
        Log.i(TAG, "OBB placeholder " + target + " (" + length + " bytes, served from the APK)");
    }

    private static boolean placeholderReady(Context c, String name) throws IOException {
        return obbTarget(c, name).length() == assetLength(c, OBB_ASSET_DIR + "/" + name)
                && (PLACEHOLDER + assetIdentity(c, name)).equals(read(identityFile(c, name)));
    }

    private static File identityFile(Context c, String name) {
        return new File(c.getFilesDir(), "obb-" + name + ".id");
    }

    /** CRC and size of the bundled entry, read from the APK's central directory (cheap). */
    private static String assetIdentity(Context c, String name) throws IOException {
        try (ZipFile apk = new ZipFile(c.getPackageCodePath())) {
            ZipEntry entry = apk.getEntry("assets/" + OBB_ASSET_DIR + "/" + name);
            if (entry == null) throw new IOException("bundled " + name + " is missing");
            return Long.toHexString(entry.getCrc()) + ":" + entry.getSize();
        }
    }

    /** main.4959.obb becomes OBB_DIR/main.4959.HOST_PACKAGE.obb. */
    private static File obbTarget(Context c, String assetName) {
        String base = assetName.endsWith(".obb") ? assetName.substring(0, assetName.length() - 4) : assetName;
        return new File(c.getObbDir(), base + "." + c.getPackageName() + ".obb");
    }

    private static String[] obbAssets(Context c) throws IOException {
        String[] names = c.getAssets().list(OBB_ASSET_DIR);
        return names != null ? names : new String[0];
    }

    private static long assetLength(Context c, String asset) throws IOException {
        try (AssetFileDescriptor afd = c.getAssets().openFd(asset)) {
            return afd.getLength();
        }
    }

    /** Changes whenever this APK is reinstalled or updated, which is when the bundle may differ. */
    private static String stamp(Context c) {
        try {
            PackageInfo info = c.getPackageManager().getPackageInfo(c.getPackageName(), 0);
            return info.getLongVersionCode() + ":" + info.lastUpdateTime;
        } catch (PackageManager.NameNotFoundException e) {
            return "unknown";
        }
    }

    private static String read(File f) {
        try {
            return new String(Files.readAllBytes(f.toPath()), StandardCharsets.UTF_8).trim();
        } catch (IOException e) {
            return null;
        }
    }

    private static void write(File f, String value) throws IOException {
        File tmp = new File(f.getPath() + ".tmp");
        Files.write(tmp.toPath(), value.getBytes(StandardCharsets.UTF_8));
        if (!tmp.renameTo(f)) throw new IOException("cannot write " + f);
    }
}
