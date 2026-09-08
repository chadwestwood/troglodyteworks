package com.troglodyteworks.trogclient.client;

import net.fabricmc.api.ClientModInitializer;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientLifecycleEvents;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientTickEvents;
import net.fabricmc.fabric.api.client.networking.v1.ClientPlayConnectionEvents;
import net.minecraft.client.Minecraft;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class TrogClientClient implements ClientModInitializer {
	public static final String MOD_ID = "trog-client";
	public static final Logger LOGGER = LoggerFactory.getLogger(MOD_ID);

	private static final int HEARTBEAT_TICKS = 20 * 60;

	private TrogApiClient apiClient;
	private boolean observingConfiguredWorld;
	private int heartbeatTicks;

	@Override
	public void onInitializeClient() {
		TrogClientConfig config = TrogClientConfig.load();
		apiClient = new TrogApiClient(config);

		ClientLifecycleEvents.CLIENT_STARTED.register(client ->
			apiClient.initialize().thenRun(() -> client.execute(() -> {
				apiClient.sendEvent("client.started", null);
				observeCurrentWorld(client);
			}))
		);
		ClientPlayConnectionEvents.JOIN.register((handler, sender, client) -> observeCurrentWorld(client));
		ClientPlayConnectionEvents.DISCONNECT.register((handler, client) -> stopObservingWorld());
		ClientTickEvents.END_CLIENT_TICK.register(this::tick);
		ClientLifecycleEvents.CLIENT_STOPPING.register(client -> {
			if (observingConfiguredWorld) {
				apiClient.sendEventAndWait("world.left", null);
			}
			apiClient.sendEventAndWait("client.stopped", null);
		});
	}

	private void observeCurrentWorld(Minecraft client) {
		WorldObservation observation = WorldObservation.current(client, apiClient.config());
		if (observation == null) {
			return;
		}
		observingConfiguredWorld = true;
		heartbeatTicks = 0;
		apiClient.sendEvent("world.joined", observation.payload());
	}

	private void stopObservingWorld() {
		if (!observingConfiguredWorld) {
			return;
		}
		observingConfiguredWorld = false;
		heartbeatTicks = 0;
		apiClient.sendEvent("world.left", null);
	}

	private void tick(Minecraft client) {
		if (!observingConfiguredWorld || ++heartbeatTicks < HEARTBEAT_TICKS) {
			return;
		}
		heartbeatTicks = 0;
		WorldObservation observation = WorldObservation.current(client, apiClient.config());
		if (observation == null) {
			stopObservingWorld();
			return;
		}
		apiClient.sendEvent("heartbeat", observation.payload());
	}
}
