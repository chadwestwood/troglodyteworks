package com.troglodyteworks.trogclient.client;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import net.fabricmc.loader.api.FabricLoader;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.time.Instant;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

final class TrogApiClient {
	private static final Duration REQUEST_TIMEOUT = Duration.ofSeconds(10);

	private final TrogClientConfig config;
	private final HttpClient httpClient;

	TrogApiClient(TrogClientConfig config) {
		this.config = config;
		this.httpClient = HttpClient.newBuilder()
			.connectTimeout(REQUEST_TIMEOUT)
			.followRedirects(HttpClient.Redirect.NEVER)
			.build();
	}

	TrogClientConfig config() {
		return config;
	}

	CompletableFuture<Void> initialize() {
		if (!config.enabled) {
			return CompletableFuture.completedFuture(null);
		}
		if (hasDeviceToken()) {
			return CompletableFuture.completedFuture(null);
		}
		if (config.pairingToken == null || config.pairingToken.isBlank()) {
			TrogClientClient.LOGGER.info("Trog Client is not paired. Add a pairing token to config/trog-client.json and restart Minecraft.");
			return CompletableFuture.failedFuture(new IllegalStateException("Trog Client is not paired"));
		}

		JsonObject body = new JsonObject();
		body.addProperty("pairing_token", config.pairingToken.trim());
		body.addProperty("device_name", cleanOrDefault(config.deviceName, "Minecraft client"));
		body.addProperty("minecraft_version", versionOf("minecraft"));
		body.addProperty("mod_version", versionOf(TrogClientClient.MOD_ID));

		CompletableFuture<HttpResponse<String>> pairingRequest;
		try {
			pairingRequest = post("/minecraft-client/pair", body, null);
		} catch (RuntimeException error) {
			TrogClientClient.LOGGER.warn("Trog Client configuration is invalid: {}", rootMessage(error));
			return CompletableFuture.failedFuture(error);
		}

		return pairingRequest.thenAccept(response -> {
			if (response.statusCode() < 200 || response.statusCode() >= 300) {
				throw new IllegalStateException("Pairing was rejected with status " + response.statusCode());
			}
			String token = JsonParser.parseString(response.body())
				.getAsJsonObject().getAsJsonObject("device").get("token").getAsString();
			if (token == null || token.length() < 20) {
				throw new IllegalStateException("Pairing response did not contain a valid device credential");
			}
			config.deviceToken = token;
			config.pairingToken = "";
			config.save();
			TrogClientClient.LOGGER.info("Trog Client paired successfully.");
		}).whenComplete((ignored, error) -> {
			if (error != null) {
				TrogClientClient.LOGGER.warn("Trog Client pairing failed: {}", rootMessage(error));
			}
		});
	}

	void sendEvent(String eventType, JsonObject payload) {
		if (!config.enabled || !hasDeviceToken()) {
			return;
		}
		CompletableFuture<HttpResponse<String>> request;
		try {
			request = postEvent(eventType, payload);
		} catch (RuntimeException error) {
			TrogClientClient.LOGGER.warn("Trog Client configuration is invalid: {}", rootMessage(error));
			return;
		}
		request.thenAccept(response -> {
			if (response.statusCode() == 401) {
				TrogClientClient.LOGGER.warn("Trog Client device access was rejected. Create a new pairing token in TWE.");
			} else if (response.statusCode() < 200 || response.statusCode() >= 300) {
				TrogClientClient.LOGGER.warn("Trog Client event was rejected with status {}.", response.statusCode());
			}
		}).exceptionally(error -> {
			TrogClientClient.LOGGER.debug("Trog Client could not report an event: {}", rootMessage(error));
			return null;
		});
	}

	void sendEventAndWait(String eventType, JsonObject payload) {
		if (!config.enabled || !hasDeviceToken()) {
			return;
		}
		try {
			postEvent(eventType, payload).get(2, TimeUnit.SECONDS);
		} catch (Exception ignored) {
			TrogClientClient.LOGGER.debug("Trog Client stopped before its final presence event was acknowledged.");
		}
	}

	private CompletableFuture<HttpResponse<String>> postEvent(String eventType, JsonObject payload) {
		JsonObject event = new JsonObject();
		event.addProperty("event_id", UUID.randomUUID().toString());
		event.addProperty("event_type", eventType);
		event.addProperty("occurred_at", Instant.now().toString());
		event.add("payload", payload == null ? new JsonObject() : payload);
		JsonArray events = new JsonArray();
		events.add(event);
		JsonObject body = new JsonObject();
		body.add("events", events);
		return post("/minecraft-client/events", body, config.deviceToken);
	}

	private CompletableFuture<HttpResponse<String>> post(String path, JsonObject body, String bearerToken) {
		URI endpoint = endpoint(path);
		HttpRequest.Builder request = HttpRequest.newBuilder(endpoint)
			.timeout(REQUEST_TIMEOUT)
			.header("Content-Type", "application/json")
			.header("User-Agent", "Trog-Client/" + versionOf(TrogClientClient.MOD_ID))
			.POST(HttpRequest.BodyPublishers.ofString(body.toString()));
		if (bearerToken != null && !bearerToken.isBlank()) {
			request.header("Authorization", "Bearer " + bearerToken.trim());
		}
		return httpClient.sendAsync(request.build(), HttpResponse.BodyHandlers.ofString());
	}

	private URI endpoint(String path) {
		String base = cleanOrDefault(config.apiBaseUrl, "https://troglodyteworks.com/api/v1");
		while (base.endsWith("/")) {
			base = base.substring(0, base.length() - 1);
		}
		URI endpoint = URI.create(base + path);
		String host = endpoint.getHost();
		boolean localDevelopment = "localhost".equalsIgnoreCase(host) || "127.0.0.1".equals(host);
		if (!"https".equalsIgnoreCase(endpoint.getScheme()) && !localDevelopment) {
			throw new IllegalArgumentException("Trog Client requires HTTPS outside local development");
		}
		return endpoint;
	}

	private boolean hasDeviceToken() {
		return config.deviceToken != null && !config.deviceToken.isBlank();
	}

	private static String versionOf(String modId) {
		return FabricLoader.getInstance().getModContainer(modId)
			.map(container -> container.getMetadata().getVersion().getFriendlyString())
			.orElse("unknown");
	}

	private static String cleanOrDefault(String value, String fallback) {
		return value == null || value.isBlank() ? fallback : value.trim();
	}

	private static String rootMessage(Throwable error) {
		Throwable current = error;
		while (current.getCause() != null) {
			current = current.getCause();
		}
		return current.getMessage() == null ? current.getClass().getSimpleName() : current.getMessage();
	}
}
