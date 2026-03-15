package com.rovac.phonesensors;

public class XrceBridge {
    static { System.loadLibrary("xrce_bridge"); }

    public native boolean connect(String agentIp, String agentPort, int domainId);
    public native boolean createPublishers(boolean withCamera);
    public native boolean publishImu(
        int sec, int nsec, String frameId,
        double ox, double oy, double oz, double ow,
        double avx, double avy, double avz,
        double lax, double lay, double laz);
    public native boolean publishNavSatFix(
        int sec, int nsec, String frameId,
        int navStatus, int service,
        double lat, double lon, double alt, int covType);
    public native boolean publishCompressedImage(
        int sec, int nsec, String frameId,
        String format, byte[] data);
    public native boolean ping(int timeoutMs);
    public native boolean reconnect(boolean withCamera);
    public native void spin(int timeoutMs);
    public native void disconnect();
    public native boolean isConnected();
}
