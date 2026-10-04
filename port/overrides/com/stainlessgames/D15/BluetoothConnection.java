package com.stainlessgames.D15;

import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothDevice;
import android.bluetooth.BluetoothServerSocket;
import android.bluetooth.BluetoothSocket;
import android.content.Context;
import android.provider.Settings;
import android.util.Log;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.ByteBuffer;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.Semaphore;

/**
 * Replacement for the game's ad-hoc multiplayer transport (port/tools.py puts it in front of the
 * game's own class). Same public API and behaviour as the original, which follows Android's
 * BluetoothChat sample, with three changes:
 *
 * - Identity. The game's network layer (libDuels.so, BZ "AndroidBluetooth" NAL) registers each
 *   player under the address GetLocalBluetoothMACAddress returns and looks up every received
 *   bundle's sender in that list. Since Android 6 an app's own Bluetooth address reads as
 *   02:00:00:00:00:00 on every phone, while senders carry real addresses, so no lookup ever
 *   matched and joining timed out. Each device now uses a stable ID of its own, and on connect
 *   both sides swap IDs in a hello frame, so the sender of every bundle is the peer's ID.
 * - Framing. Frames are read whole: RFCOMM delivers at most about 1 KB per read, and the original
 *   assumed one read per frame.
 * - The host's session descriptor (mBznetstruct) is cleared between attempts.
 */
public class BluetoothConnection {
    public static final int BZANDROIDBT_STATE_NONE = 0;
    public static final int BZANDROIDBT_STATE_CONNECTING = 1;
    public static final int BZANDROIDBT_STATE_CONNECTED = 2;
    public static final int BZANDROIDBT_STATE_HOST = 3;
    public static final int BZANDROIDBT_STATE_CLIENT = 4;

    private static final String TAG = "AndroidSGTest";
    private static final String ZB_TAG = "zb-bluetooth";
    private static final String NAME_SECURE = "TestAppSecure";
    private static final String NAME_INSECURE = "TestAppInsecure";
    private static final UUID MY_UUID_SECURE = UUID.fromString("fa87c0d0-afac-11de-8a39-0800200c9a67");
    private static final UUID MY_UUID_INSECURE = UUID.fromString("8ce255c0-200a-11e0-ac64-0800200c9a67");

    /** Largest frame the game sends; the original read buffer. */
    private static final int MAX_FRAME = 8192;
    /** First frame on every connection: "ZBID" and the sender's 12-character ID. */
    private static final byte[] HELLO_MAGIC = {'Z', 'B', 'I', 'D'};
    private static final int ID_LENGTH = 12;

    private static String sLocalId;

    private BluetoothAdapter mBluetoothAdapter;
    private int mBluetoothState = BZANDROIDBT_STATE_NONE;
    private byte[] mBznetstruct;
    private ConnectThread mConnectThread;
    private ConnectedThread mConnectedThread;
    private AcceptThread mInsecureAcceptThread;
    private boolean mIsHost;
    private final Semaphore mProcessingBundle = new Semaphore(1);
    final List<ReceivedBundle> mQueuedBundles = Collections.synchronizedList(new ArrayList<ReceivedBundle>());
    private AcceptThread mSecureAcceptThread;

    public BluetoothConnection() {
    }

    /**
     * This device's ID in the game's network layer, in the format the original produced from the
     * adapter address (12 upper-case hex digits). Derived from ANDROID_ID, so it stays the same
     * across launches; marked as a locally administered address so it cannot equal a real one.
     */
    public String GetLocalBluetoothMACAddress() {
        return localId();
    }

    static synchronized String localId() {
        if (sLocalId != null) return sLocalId;
        byte[] bytes = new byte[6];
        try {
            Context app = (Context) Class.forName("android.app.ActivityThread")
                    .getMethod("currentApplication").invoke(null);
            String androidId = Settings.Secure.getString(app.getContentResolver(), Settings.Secure.ANDROID_ID);
            if (androidId == null) throw new IllegalStateException("no ANDROID_ID");
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(
                    ("magic2015-bluetooth:" + androidId).getBytes("UTF-8"));
            System.arraycopy(digest, 0, bytes, 0, 6);
        } catch (Exception e) {
            Log.w(ZB_TAG, "no ANDROID_ID, using a random Bluetooth ID for this run", e);
            new SecureRandom().nextBytes(bytes);
        }
        bytes[0] = (byte) ((bytes[0] & 0xFC) | 0x02);  // locally administered, unicast
        StringBuilder id = new StringBuilder();
        for (byte b : bytes) id.append(String.format("%02X", b & 0xFF));
        sLocalId = id.toString();
        Log.i(ZB_TAG, "local Bluetooth ID " + sLocalId);
        return sLocalId;
    }

    public byte[] getBZSession() {
        return mBznetstruct;
    }

    public int getStatus() {
        if (mBluetoothState != BZANDROIDBT_STATE_CONNECTED) return mBluetoothState;
        if (!mIsHost && mBznetstruct == null) return BZANDROIDBT_STATE_CONNECTING;
        return mIsHost ? BZANDROIDBT_STATE_HOST : BZANDROIDBT_STATE_CLIENT;
    }

    public void openClientSocket(BluetoothDevice device) {
        Log.d("bz_debug", "native_connectToBluetoothSocket");
        mBznetstruct = null;
        mConnectThread = new ConnectThread(device, true);
        mConnectThread.start();
        mIsHost = false;
    }

    public void openServerSocket() {
        Log.d("bz_debug", "native_openBluetoothSocket");
        mBznetstruct = null;
        if (mSecureAcceptThread == null) {
            mSecureAcceptThread = new AcceptThread(true);
            mSecureAcceptThread.start();
        }
        mIsHost = true;
    }

    public boolean receiveBundle_bundlesAvailable() {
        return mQueuedBundles.size() > 0;
    }

    public void receiveBundle_clearLast() {
        mQueuedBundles.remove(0);
        mProcessingBundle.release();
    }

    public byte[] receiveBundle_data() {
        while (true) {
            try {
                mProcessingBundle.acquire();
                break;
            } catch (InterruptedException e) {
                e.printStackTrace();
            }
        }
        return mQueuedBundles.get(0).mBytes;
    }

    public String receiveBundle_senderAddress() {
        return mQueuedBundles.get(0).mSenderAddress;
    }

    public void sendMessage(byte[] message) {
        ConnectedThread connected;
        synchronized (this) {
            if (mBluetoothState < BZANDROIDBT_STATE_CONNECTED) return;
            connected = mConnectedThread;
        }
        connected.write(message);
    }

    public synchronized void startConnectedThread(BluetoothSocket socket, BluetoothDevice device, String socketType) {
        Log.d(TAG, "connected, Socket Type:" + socketType);
        if (mConnectThread != null) {
            mConnectThread.cancel();
            mConnectThread = null;
        }
        if (mConnectedThread != null) {
            mConnectedThread.cancel();
            mConnectedThread = null;
        }
        if (mSecureAcceptThread != null) {
            mSecureAcceptThread.cancel();
            mSecureAcceptThread = null;
        }
        if (mInsecureAcceptThread != null) {
            mInsecureAcceptThread.cancel();
            mInsecureAcceptThread = null;
        }
        mConnectedThread = new ConnectedThread(socket, socketType);
        mConnectedThread.start();
    }

    public void stopAndCleanup() {
        if (mConnectThread != null) {
            mConnectThread.cancel();
            mConnectThread = null;
        }
        if (mConnectedThread != null) {
            mConnectedThread.cancel();
            mConnectedThread = null;
        }
        if (mSecureAcceptThread != null) {
            mSecureAcceptThread.cancel();
            mSecureAcceptThread = null;
        }
        mBluetoothState = BZANDROIDBT_STATE_NONE;
        mBznetstruct = null;
        mQueuedBundles.clear();
    }

    private static void readFully(InputStream in, byte[] buffer, int length) throws IOException {
        int done = 0;
        while (done < length) {
            int n = in.read(buffer, done, length - done);
            if (n < 0) throw new IOException("bt socket closed");
            done += n;
        }
    }

    private class AcceptThread extends Thread {
        private final BluetoothServerSocket mmServerSocket;
        private final String mSocketType;

        AcceptThread(boolean secure) {
            BluetoothServerSocket socket = null;
            mSocketType = secure ? "Secure" : "Insecure";
            mBluetoothAdapter = BluetoothAdapter.getDefaultAdapter();
            try {
                socket = secure
                        ? mBluetoothAdapter.listenUsingRfcommWithServiceRecord(NAME_SECURE, MY_UUID_SECURE)
                        : mBluetoothAdapter.listenUsingInsecureRfcommWithServiceRecord(NAME_INSECURE, MY_UUID_INSECURE);
            } catch (IOException e) {
                Log.e(TAG, "Socket Type: " + mSocketType + "listen() failed", e);
            }
            mmServerSocket = socket;
        }

        @Override
        public void run() {
            Log.d(TAG, "Socket Type: " + mSocketType + "BEGIN mAcceptThread" + this);
            setName("AcceptThread" + mSocketType);
            mBluetoothState = BZANDROIDBT_STATE_CONNECTING;
            while (mBluetoothState != BZANDROIDBT_STATE_CONNECTED) {
                BluetoothSocket socket;
                try {
                    socket = mmServerSocket.accept();
                } catch (IOException e) {
                    Log.e(TAG, "Socket Type: " + mSocketType + "accept() failed", e);
                    break;
                }
                if (socket != null) {
                    synchronized (BluetoothConnection.this) {
                        startConnectedThread(socket, socket.getRemoteDevice(), mSocketType);
                    }
                    Log.i(TAG, "CONNECTED, socket Type: " + mSocketType);
                }
            }
            Log.i(TAG, "END mAcceptThread, socket Type: " + mSocketType);
        }

        void cancel() {
            Log.d(TAG, "Socket Type" + mSocketType + "cancel " + this);
            try {
                mmServerSocket.close();
            } catch (IOException | NullPointerException e) {
                Log.e(TAG, "Socket Type" + mSocketType + "close() of server failed", e);
            }
        }
    }

    private class ConnectThread extends Thread {
        private final BluetoothDevice mmDevice;
        private final BluetoothSocket mmSocket;
        private final String mSocketType;

        ConnectThread(BluetoothDevice device, boolean secure) {
            mmDevice = device;
            BluetoothSocket socket = null;
            mSocketType = secure ? "Secure" : "Insecure";
            try {
                socket = secure
                        ? device.createRfcommSocketToServiceRecord(MY_UUID_SECURE)
                        : device.createInsecureRfcommSocketToServiceRecord(MY_UUID_INSECURE);
            } catch (IOException e) {
                Log.e(TAG, "Socket Type: " + mSocketType + "create() failed", e);
            }
            mmSocket = socket;
            mBluetoothAdapter = BluetoothAdapter.getDefaultAdapter();
        }

        @Override
        public void run() {
            Log.i(TAG, "BEGIN mConnectThread SocketType:" + mSocketType);
            setName("ConnectThread" + mSocketType);
            mBluetoothAdapter.cancelDiscovery();
            mBluetoothState = BZANDROIDBT_STATE_CONNECTING;
            try {
                mmSocket.connect();
            } catch (IOException | NullPointerException e) {
                Log.e(TAG, "connect() failed", e);
                try {
                    mmSocket.close();
                    Log.i(TAG, "Calling close() 1 ");
                } catch (IOException | NullPointerException e2) {
                    Log.e(TAG, "unable to close() " + mSocketType + " socket during connection failure", e2);
                }
                return;
            }
            synchronized (BluetoothConnection.this) {
                mConnectThread = null;
            }
            Log.i(TAG, "CONNECTED, socket Type: " + mSocketType);
            startConnectedThread(mmSocket, mmDevice, mSocketType);
        }

        void cancel() {
            try {
                mmSocket.close();
                Log.i(TAG, "Calling close() 2");
            } catch (IOException | NullPointerException e) {
                Log.e(TAG, "close() of connect " + mSocketType + " socket failed", e);
            }
        }
    }

    private class ConnectedThread extends Thread {
        private final BluetoothSocket mmSocket;
        private final InputStream mmInStream;
        private final OutputStream mmOutStream;
        /** The peer's ID once its hello arrives; its Bluetooth address until then (old builds). */
        private volatile String mmRemoteAddress;

        ConnectedThread(BluetoothSocket socket, String socketType) {
            Log.d(TAG, "create ConnectedThread: " + socketType);
            mmSocket = socket;
            InputStream in = null;
            OutputStream out = null;
            try {
                in = socket.getInputStream();
                out = socket.getOutputStream();
            } catch (IOException e) {
                Log.e(TAG, "temp sockets not created", e);
            }
            mmInStream = in;
            mmOutStream = out;
            mmRemoteAddress = socket.getRemoteDevice().getAddress().replace(":", "");
            // The hello goes out before the state says connected, so it precedes every game frame.
            byte[] hello = new byte[HELLO_MAGIC.length + ID_LENGTH];
            System.arraycopy(HELLO_MAGIC, 0, hello, 0, HELLO_MAGIC.length);
            byte[] id = localId().getBytes();
            System.arraycopy(id, 0, hello, HELLO_MAGIC.length, ID_LENGTH);
            write(hello);
            mBluetoothState = BZANDROIDBT_STATE_CONNECTED;
        }

        @Override
        public void run() {
            Log.i(TAG, "BEGIN mConnectedThread");
            byte[] size = new byte[4];
            byte[] buffer = new byte[MAX_FRAME];
            boolean first = true;
            try {
                while (true) {
                    readFully(mmInStream, size, 4);
                    int length = ByteBuffer.wrap(size).getInt();
                    if (length < 0 || length > MAX_FRAME) {
                        Log.e(ZB_TAG, "skipping a frame of " + length + " bytes");
                        for (long left = length & 0xFFFFFFFFL; left > 0; ) {
                            int n = (int) Math.min(left, MAX_FRAME);
                            readFully(mmInStream, buffer, n);
                            left -= n;
                        }
                        continue;
                    }
                    readFully(mmInStream, buffer, length);
                    if (first) {
                        first = false;
                        if (isHello(buffer, length)) {
                            mmRemoteAddress = new String(buffer, HELLO_MAGIC.length, ID_LENGTH, "US-ASCII");
                            Log.i(ZB_TAG, "peer Bluetooth ID " + mmRemoteAddress);
                            continue;
                        }
                        Log.w(ZB_TAG, "peer sent no ID (an older build?); using its Bluetooth address");
                    }
                    if (length >= 4 && buffer[0] == -1 && buffer[1] == -2 && buffer[2] == -3 && buffer[3] == -4) {
                        byte[] session = new byte[length - 4];
                        System.arraycopy(buffer, 4, session, 0, length - 4);
                        mBznetstruct = session;
                        continue;
                    }
                    ReceivedBundle bundle = new ReceivedBundle();
                    bundle.mBytes = new byte[length];
                    System.arraycopy(buffer, 0, bundle.mBytes, 0, length);
                    bundle.mNumBytes = length;
                    bundle.mSenderAddress = mmRemoteAddress;
                    try {
                        mProcessingBundle.acquire();
                        mQueuedBundles.add(bundle);
                        mProcessingBundle.release();
                    } catch (InterruptedException e) {
                        e.printStackTrace();
                    }
                }
            } catch (IOException e) {
                Log.e(TAG, "disconnected", e);
            }
        }

        private boolean isHello(byte[] frame, int length) {
            if (length != HELLO_MAGIC.length + ID_LENGTH) return false;
            for (int i = 0; i < HELLO_MAGIC.length; i++) {
                if (frame[i] != HELLO_MAGIC[i]) return false;
            }
            return true;
        }

        void write(byte[] message) {
            byte[] frame = new byte[4 + message.length];
            ByteBuffer.wrap(frame).putInt(message.length).put(message);
            try {
                synchronized (mmOutStream) {
                    mmOutStream.write(frame);
                }
            } catch (IOException | NullPointerException e) {
                Log.e(TAG, "Exception during write", e);
            }
        }

        void cancel() {
            try {
                mmSocket.close();
            } catch (IOException e) {
                Log.e(TAG, "close() of connect socket failed", e);
            }
        }
    }

    class ReceivedBundle {
        byte[] mBytes;
        int mNumBytes;
        String mSenderAddress;
    }
}
