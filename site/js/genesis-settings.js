async function loadGenesisSettings() {
  const response = await fetch('/api/genesis/settings');
  const data = await response.json();
  renderGenesisSettings(data);
}

async function loadPlayers() {
  const response = await fetch('/api/genesis/players');
  const data = await response.json();

  setText('players-online', data.online ?? 0);

  const list = document.getElementById('players-list');
  if (!list) return;

  list.innerHTML = '';

  if (!data.success || !data.players || data.players.length === 0) {
    list.innerHTML = '<li>No players online</li>';
    return;
  }

  data.players.forEach(player => {
    const li = document.createElement('li');
    li.textContent = player;
    list.appendChild(li);
  });
}

async function refreshGenesisSettings() {
  setTrog('Refreshing Genesis dashboard...');

  const response = await fetch('/api/genesis/actions/refresh', {
    method: 'POST'
  });

  const result = await response.json();

  if (!result.success) {
    setTrog('Refresh failed.');
    return;
  }

  renderGenesisSettings(result.data);
  await loadPlayers();
  setTrog('Genesis dashboard refreshed.');
}

function renderGenesisSettings(data) {
  const settings = data.settings;
  const profile = data.profile;

  setText('harvest', `${settings.HarvestAmountMultiplier ?? 'Unknown'}x`);
  setText('taming', `${settings.TamingSpeedMultiplier ?? 'Unknown'}x`);
  setText('maxPlayers', settings.MaxPlayers ?? 'Unknown');
  setText('mature', `${settings.BabyMatureSpeedMultiplier ?? 'Unknown'}x`);
  setText('hatch', `${settings.EggHatchSpeedMultiplier ?? 'Unknown'}x`);
  setText('difficulty', settings.OverrideOfficialDifficulty ?? 'Unknown');

  setProfile('harvest', profile.harvesting);
  setProfile('taming', profile.taming);
  setProfile('mature', profile.baby_mature);
  setProfile('hatch', profile.egg_hatch);
  setProfile('difficulty', profile.difficulty);

  setTrogMessage(profile);
}

function setText(key, value) {
  const el = document.querySelector(`[data-setting="${key}"]`);
  if (el) el.textContent = value;
}

function setProfile(key, data) {
  if (!data) return;

  setText(`${key}-label`, data.label);
  setText(`${key}-stars`, stars(data.stars));
  setText(`${key}-description`, data.description);
}

function stars(count) {
  const full = '★'.repeat(count || 0);
  const empty = '☆'.repeat(5 - (count || 0));
  return full + empty;
}

function setTrog(message) {
  const el = document.getElementById('trog-message');
  if (el) el.textContent = message;
}

function setTrogMessage(profile) {
  const harvesting = profile.harvesting?.label ?? 'Unknown';
  const taming = profile.taming?.label ?? 'Unknown';
  const breeding = profile.baby_mature?.label ?? 'Unknown';

  setTrog(
    `Your Genesis world feels like a ${harvesting} server with ${taming.toLowerCase()} taming and ${breeding.toLowerCase()} breeding.`
  );
}

document.addEventListener('DOMContentLoaded', () => {
  loadGenesisSettings().catch(console.error);
  loadPlayers().catch(console.error);

  const refreshButton = document.getElementById('refresh-settings');
  if (refreshButton) {
    refreshButton.addEventListener('click', refreshGenesisSettings);
  }
});
