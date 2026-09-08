package com.troglodyteworks.trogclient.client;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import net.fabricmc.loader.api.FabricLoader;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

final class TrogClientConfig {
	private static final Gson GSON = new GsonBuilder().setPrettyPrinting().create();
	private static final Path PATH = FabricLoader.getInstance().getConfigDir().resolve("trog-client.json");

	boolean enabled = true;
	String apiBaseUrl = "https://troglodyteworks.com/api/v1";
	String pairingToken = "";
	String deviceToken = "";
	String deviceName = "Minecraft client";
	String worldLabel = "Minecraft City";
	String serverAddress = "";

	static TrogClientConfig load() {
		if (!Files.exists(PATH)) {
			TrogClientConfig created = new TrogClientConfig();
			created.save();
			TrogClientClient.LOGGER.info("Created Trog Client configuration at {}", PATH);
			return created;
		}
		try {
			TrogClientConfig loaded = GSON.fromJson(Files.readString(PATH, StandardCharsets.UTF_8), TrogClientConfig.class);
			return loaded == null ? new TrogClientConfig() : loaded;
		} catch (Exception exception) {
			TrogClientClient.LOGGER.error("Trog Client configuration could not be read; reporting is disabled.", exception);
			TrogClientConfig disabled = new TrogClientConfig();
			disabled.enabled = false;
			return disabled;
		}
	}

	synchronized void save() {
		try {
			Files.createDirectories(PATH.getParent());
			Path temporary = Files.createTempFile(PATH.getParent(), ".trog-client-", ".json");
			Files.writeString(temporary, GSON.toJson(this), StandardCharsets.UTF_8);
			try {
				Files.move(temporary, PATH, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
			} catch (IOException unsupportedAtomicMove) {
				Files.move(temporary, PATH, StandardCopyOption.REPLACE_EXISTING);
			}
		} catch (IOException exception) {
			TrogClientClient.LOGGER.error("Trog Client configuration could not be saved.", exception);
		}
	}

	boolean isConfiguredWorld(String address) {
		return enabled
			&& serverAddress != null
			&& !serverAddress.isBlank()
			&& normalizeAddress(serverAddress).equals(normalizeAddress(address));
	}

	private static String normalizeAddress(String address) {
		return address == null ? "" : address.trim().toLowerCase();
	}
}
