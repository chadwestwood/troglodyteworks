package com.troglodyteworks.trogclient.client;

import com.google.gson.JsonObject;
import net.minecraft.client.Minecraft;
import net.minecraft.client.multiplayer.ServerData;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

record WorldObservation(String worldLabel, String serverFingerprint, String connectionKind) {
	static WorldObservation current(Minecraft client, TrogClientConfig config) {
		ServerData server = client.getCurrentServer();
		if (server == null || !config.isConfiguredWorld(server.ip)) {
			return null;
		}
		String label = config.worldLabel == null || config.worldLabel.isBlank()
			? "Configured Minecraft world"
			: config.worldLabel.trim();
		return new WorldObservation(label, sha256(config.serverAddress.trim().toLowerCase()), "multiplayer");
	}

	JsonObject payload() {
		JsonObject payload = new JsonObject();
		payload.addProperty("world_label", worldLabel);
		payload.addProperty("server_fingerprint", serverFingerprint);
		payload.addProperty("connection_kind", connectionKind);
		return payload;
	}

	private static String sha256(String value) {
		try {
			return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8)));
		} catch (NoSuchAlgorithmException impossible) {
			throw new IllegalStateException("SHA-256 is unavailable", impossible);
		}
	}
}
