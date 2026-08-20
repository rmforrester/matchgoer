import type { NextConfig } from "next";
import os from "os";

const networkInterfaces = os.networkInterfaces();

const localNetworkAddresses = Object.values(networkInterfaces)
  .flatMap((addresses) => addresses ?? [])
  .filter(
    (address) =>
      address.family === "IPv4" &&
      !address.internal
  )
  .map((address) => address.address);

const nextConfig: NextConfig = {
  allowedDevOrigins: [
    "localhost",
    "127.0.0.1",
    ...localNetworkAddresses,
  ],
};

export default nextConfig;