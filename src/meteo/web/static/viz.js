/* Graphe de vérification : ce que chaque modèle annonçait, face à ce qui a été mesuré.
 *
 * Rendu SVG sans dépendance externe. Trois interactions : zoom temporel (glisser,
 * molette, double-clic pour revenir), bascule d'une série depuis la légende, et
 * lecture au survol qui affiche toutes les séries à la date pointée.
 *
 * Les couleurs vivent dans viz.css, jamais ici : le mode sombre bascule sans
 * recalcul, et une série garde sa teinte quand on en masque d'autres.
 */
(function () {
  'use strict';

  var racine = document.querySelector('[data-viz]');
  if (!racine) return;

  var LARGEUR = 900, HAUTEUR_LIGNES = 340;
  var M = { gauche: 46, droite: 14, haut: 14, bas: 34 };
  var SVGNS = 'http://www.w3.org/2000/svg';

  // Mode bandes (pluie) : une rangée par série, plus large à gauche pour les noms.
  var BANDE = { hauteur: 18, espace: 10, gauche: 104, separation: 14 };

  var HAUTEUR = HAUTEUR_LIGNES;
  var MARGE_GAUCHE = M.gauche;

  var etat = {
    donnees: null,
    debut: 0,
    fin: 0,
    masquees: new Set(),
    jours: parseInt(racine.dataset.jours, 10) || 14,
    station: racine.dataset.station,
    anticipation: parseInt(racine.dataset.anticipation, 10) || 1,
    saison: racine.dataset.saison || '',
    variable: racine.dataset.variable || 'temperature'
  };

  function estPluie() { return etat.donnees && etat.donnees.variable === 'pluie'; }

  function aPlu(v) {
    return v !== null && v !== undefined && v >= etat.donnees.seuil_pluie_mm;
  }

  function formatValeur(v) {
    if (v === null || v === undefined) return '—';
    return estPluie() ? v.toFixed(1) + ' mm' : v.toFixed(1) + ' °C';
  }

  var cadre = racine.querySelector('.viz-cadre');
  var legende = racine.querySelector('.viz-legende');
  var bulle = racine.querySelector('.viz-bulle');
  var corpsTableau = racine.querySelector('.viz-tableau tbody');
  var teteTableau = racine.querySelector('.viz-tableau thead tr');
  var indice = racine.querySelector('.viz-commandes .indice');
  var svg = null;

  function el(nom, attrs) {
    var n = document.createElementNS(SVGNS, nom);
    for (var k in attrs) n.setAttribute(k, attrs[k]);
    return n;
  }

  function classeSerie(i) {
    return i < 0 ? 'observe' : 's' + ((i % 6) + 1);
  }

  /* --- Séries visibles, bornes, échelles ------------------------------------ */

  function series() {
    var s = [{ nom: 'Mesuré', valeurs: etat.donnees.observations, classe: 'observe' }];
    etat.donnees.previsions.forEach(function (p, i) {
      s.push({ nom: p.nom, valeurs: p.valeurs, classe: classeSerie(i) });
    });
    return s;
  }

  function visibles() {
    return series().filter(function (s) { return !etat.masquees.has(s.nom); });
  }

  function bornes(liste) {
    var bas = Infinity, haut = -Infinity;
    liste.forEach(function (s) {
      for (var i = etat.debut; i <= etat.fin; i++) {
        var v = s.valeurs[i];
        if (v === null || v === undefined) continue;
        if (v < bas) bas = v;
        if (v > haut) haut = v;
      }
    });
    if (!isFinite(bas)) return [0, 1];
    if (haut - bas < 1) haut = bas + 1;
    var marge = (haut - bas) * 0.08;
    return [bas - marge, haut + marge];
  }

  function graduationsY(bas, haut) {
    var brut = (haut - bas) / 4;
    var magnitude = Math.pow(10, Math.floor(Math.log10(brut)));
    var pas = [1, 2, 2.5, 5, 10].map(function (m) { return m * magnitude; })
      .find(function (p) { return p >= brut; }) || magnitude * 10;
    var ticks = [], v = Math.ceil(bas / pas) * pas;
    for (; v <= haut; v += pas) ticks.push(Math.round(v * 1e6) / 1e6);
    return ticks;
  }

  /* Les graduations tombent sur des repères lisibles — minuit, ou une heure ronde
     quand la fenêtre couvre moins d'une journée — jamais à un pas arbitraire. */
  function graduationsX(n) {
    var instants = etat.donnees.instants;
    var candidats = [];
    for (var i = etat.debut; i <= etat.fin; i++) {
      var h = new Date(instants[i]).getHours();
      if (h === 0) candidats.push(i);
    }
    if (candidats.length < 2) {
      candidats = [];
      for (var j = etat.debut; j <= etat.fin; j++) {
        if (new Date(instants[j]).getHours() % 6 === 0) candidats.push(j);
      }
    }
    if (candidats.length < 2) candidats = [etat.debut, etat.fin];

    var pas = Math.ceil(candidats.length / 8);
    return candidats.filter(function (_, k) { return k % pas === 0; });
  }

  function formatDate(iso, avecHeure) {
    var d = new Date(iso);
    var jour = String(d.getDate()).padStart(2, '0') + '/' + String(d.getMonth() + 1).padStart(2, '0');
    return avecHeure ? jour + ' ' + String(d.getHours()).padStart(2, '0') + 'h' : jour;
  }

  /* --- Rendu ---------------------------------------------------------------- */

  function rendre() {
    var d = etat.donnees;
    var n = etat.fin - etat.debut + 1;
    cadre.textContent = '';

    if (!d || n < 2) {
      var p = document.createElement('p');
      p.className = 'viz-vide';
      p.textContent = "Pas encore assez de données pour tracer la vérification.";
      cadre.appendChild(p);
      return;
    }

    if (estPluie()) { rendreBandes(n); return; }
    rendreLignes(n);
  }

  /* Pluie : une rangée par série, colorée aux heures annoncées pluvieuses.
     Le verdict sur la pluie est binaire — fausses alertes et pluies manquées —
     et cette forme les rend visibles sans lire un chiffre. */
  function rendreBandes(n) {
    var d = etat.donnees;
    var vis = visibles();
    HAUTEUR = M.haut + vis.length * (BANDE.hauteur + BANDE.espace)
      + BANDE.separation + M.bas;
    MARGE_GAUCHE = BANDE.gauche;
    var utileX = LARGEUR - MARGE_GAUCHE - M.droite;

    function x(i) { return MARGE_GAUCHE + ((i - etat.debut) / (n - 1)) * utileX; }
    function largeur(a, z) { return Math.max(1.5, x(z + 1) - x(a)); }

    svg = el('svg', {
      viewBox: '0 0 ' + LARGEUR + ' ' + HAUTEUR,
      role: 'img',
      'aria-label': 'Heures de pluie annoncées par chaque modèle et heures de pluie mesurées, du '
        + formatDate(d.instants[etat.debut]) + ' au ' + formatDate(d.instants[etat.fin])
    });

    vis.forEach(function (s, rang) {
      var y = M.haut + rang * (BANDE.hauteur + BANDE.espace)
        + (rang > 0 ? BANDE.separation : 0);

      svg.appendChild(el('rect', {
        class: 'viz-bande-fond', x: MARGE_GAUCHE, y: y,
        width: utileX, height: BANDE.hauteur, rx: 3
      }));

      var nom = el('text', {
        class: 'viz-bande-nom', x: MARGE_GAUCHE - 10, y: y + BANDE.hauteur - 5
      });
      nom.textContent = s.nom;
      svg.appendChild(nom);

      plages(s.valeurs).forEach(function (pl) {
        svg.appendChild(el('rect', {
          class: 'viz-bande ' + s.classe, x: x(pl[0]), y: y,
          width: largeur(pl[0], pl[1]), height: BANDE.hauteur, rx: 2
        }));
      });
    });

    var basAxe = HAUTEUR - M.bas;
    svg.appendChild(el('line', {
      class: 'viz-axe-ligne', x1: MARGE_GAUCHE, x2: LARGEUR - M.droite,
      y1: basAxe, y2: basAxe
    }));
    graduationsX(n).forEach(function (i) {
      var t = el('text', { class: 'viz-graduation x', x: x(i), y: HAUTEUR - 12 });
      t.textContent = formatDate(d.instants[i], n <= 72);
      svg.appendChild(t);
    });

    var couche = el('g', { class: 'viz-couche' });
    svg.appendChild(couche);
    cadre.appendChild(svg);

    brancherPointeur(svg, couche, x, null, n);
    majIndice();
    majTableau();
  }

  /* Regroupe les heures pluvieuses consécutives en plages [début, fin]. */
  function plages(valeurs) {
    var out = [], debut = null;
    for (var i = etat.debut; i <= etat.fin; i++) {
      if (aPlu(valeurs[i])) {
        if (debut === null) debut = i;
      } else if (debut !== null) {
        out.push([debut, i - 1]);
        debut = null;
      }
    }
    if (debut !== null) out.push([debut, etat.fin]);
    return out;
  }

  function rendreLignes(n) {
    var d = etat.donnees;
    HAUTEUR = HAUTEUR_LIGNES;
    MARGE_GAUCHE = M.gauche;
    var vis = visibles();
    var b = bornes(vis.length ? vis : series());
    var bas = b[0], haut = b[1];
    var utileX = LARGEUR - MARGE_GAUCHE - M.droite;
    var utileY = HAUTEUR - M.haut - M.bas;

    function x(i) { return MARGE_GAUCHE + ((i - etat.debut) / (n - 1)) * utileX; }
    function y(v) { return M.haut + ((haut - v) / (haut - bas)) * utileY; }

    svg = el('svg', {
      viewBox: '0 0 ' + LARGEUR + ' ' + HAUTEUR,
      role: 'img',
      'aria-label': 'Températures annoncées par chaque modèle et température mesurée, ' +
        'du ' + formatDate(d.instants[etat.debut]) + ' au ' + formatDate(d.instants[etat.fin])
    });

    graduationsY(bas, haut).forEach(function (v) {
      svg.appendChild(el('line', {
        class: 'viz-grille-ligne', x1: M.gauche, x2: LARGEUR - M.droite, y1: y(v), y2: y(v)
      }));
      var t = el('text', { class: 'viz-graduation y', x: M.gauche - 8, y: y(v) + 4 });
      t.textContent = v + '°';
      svg.appendChild(t);
    });

    svg.appendChild(el('line', {
      class: 'viz-axe-ligne', x1: M.gauche, x2: LARGEUR - M.droite,
      y1: HAUTEUR - M.bas, y2: HAUTEUR - M.bas
    }));

    graduationsX(n).forEach(function (i) {
      var t = el('text', { class: 'viz-graduation x', x: x(i), y: HAUTEUR - 12 });
      t.textContent = formatDate(d.instants[i], n <= 72);
      svg.appendChild(t);
    });

    // Les prévisions d'abord, la mesure par-dessus : c'est elle qui fait foi.
    vis.slice(1).concat(vis[0] && vis[0].classe === 'observe' ? [vis[0]] : [])
      .forEach(function (s) {
        troncons(s.valeurs).forEach(function (tr) {
          svg.appendChild(el('polyline', {
            class: 'viz-serie ' + s.classe,
            points: tr.map(function (pt) { return x(pt[0]).toFixed(1) + ',' + y(pt[1]).toFixed(1); }).join(' ')
          }));
        });
      });

    var couche = el('g', { class: 'viz-couche' });
    svg.appendChild(couche);
    cadre.appendChild(svg);

    brancherPointeur(svg, couche, x, y, n);
    majIndice();
    majTableau();
  }

  function troncons(valeurs) {
    var out = [], courant = [];
    for (var i = etat.debut; i <= etat.fin; i++) {
      var v = valeurs[i];
      if (v === null || v === undefined) {
        if (courant.length > 1) out.push(courant);
        courant = [];
      } else {
        courant.push([i, v]);
      }
    }
    if (courant.length > 1) out.push(courant);
    return out;
  }

  function majIndice() {
    var d = etat.donnees;
    indice.textContent = formatDate(d.instants[etat.debut]) + ' → ' +
      formatDate(d.instants[etat.fin]) + '  ·  ' + (etat.fin - etat.debut + 1) + ' heures';
  }

  /* --- Survol : une lecture, toutes les séries ------------------------------ */

  function brancherPointeur(svg, couche, x, y, n) {
    function indexDe(evt) {
      var boite = svg.getBoundingClientRect();
      var px = (evt.clientX - boite.left) / boite.width * LARGEUR;
      var ratio = (px - MARGE_GAUCHE) / (LARGEUR - MARGE_GAUCHE - M.droite);
      return Math.max(etat.debut, Math.min(etat.fin,
        etat.debut + Math.round(ratio * (n - 1))));
    }

    var glisse = null;

    svg.addEventListener('pointermove', function (evt) {
      var i = indexDe(evt);
      if (glisse !== null) {
        dessinerSelection(couche, x, Math.min(glisse, i), Math.max(glisse, i));
      } else {
        dessinerCurseur(couche, x, y, i);
        remplirBulle(i, evt);
      }
    });

    svg.addEventListener('pointerleave', function () {
      couche.textContent = '';
      bulle.dataset.visible = 'false';
    });

    svg.addEventListener('pointerdown', function (evt) {
      glisse = indexDe(evt);
      svg.setPointerCapture(evt.pointerId);
      bulle.dataset.visible = 'false';
    });

    svg.addEventListener('pointerup', function (evt) {
      if (glisse === null) return;
      var i = indexDe(evt);
      var a = Math.min(glisse, i), z = Math.max(glisse, i);
      glisse = null;
      couche.textContent = '';
      if (z - a >= 3) { etat.debut = a; etat.fin = z; rendre(); }
    });

    svg.addEventListener('dblclick', reinitialiserZoom);

    svg.addEventListener('wheel', function (evt) {
      evt.preventDefault();
      var i = indexDe(evt);
      var etendue = etat.fin - etat.debut;
      var facteur = evt.deltaY < 0 ? 0.75 : 1 / 0.75;
      var nouvelle = Math.max(6, Math.round(etendue * facteur));
      var part = (i - etat.debut) / etendue;
      var a = Math.round(i - part * nouvelle);
      var z = a + nouvelle;
      etat.debut = Math.max(0, a);
      etat.fin = Math.min(etat.donnees.instants.length - 1, z);
      if (etat.fin - etat.debut < 6) return;
      rendre();
    }, { passive: false });
  }

  function dessinerCurseur(couche, x, y, i) {
    couche.textContent = '';
    couche.appendChild(el('line', {
      class: 'viz-curseur', x1: x(i), x2: x(i), y1: M.haut, y2: HAUTEUR - M.bas
    }));
    // En mode bandes il n'y a pas d'échelle verticale : la ligne suffit.
    if (!y) return;
    visibles().forEach(function (s) {
      var v = s.valeurs[i];
      if (v === null || v === undefined) return;
      var c = el('circle', { class: 'viz-point ' + s.classe, cx: x(i), cy: y(v), r: 4 });
      c.style.fill = getComputedStyle(document.documentElement)
        .getPropertyValue(s.classe === 'observe' ? '--viz-ink' : '--serie-' + s.classe.slice(1)) || 'currentColor';
      couche.appendChild(c);
    });
  }

  function dessinerSelection(couche, x, a, z) {
    couche.textContent = '';
    couche.appendChild(el('rect', {
      class: 'viz-selection', x: x(a), y: M.haut,
      width: Math.max(1, x(z) - x(a)), height: HAUTEUR - M.haut - M.bas
    }));
  }

  function remplirBulle(i, evt) {
    var d = etat.donnees;
    bulle.textContent = '';

    var quand = document.createElement('div');
    quand.className = 'quand';
    quand.textContent = new Date(d.instants[i]).toLocaleString('fr-FR', {
      weekday: 'short', day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit'
    });
    bulle.appendChild(quand);

    var table = document.createElement('table');
    var tbody = document.createElement('tbody');
    visibles().forEach(function (s) {
      var v = s.valeurs[i];
      var tr = document.createElement('tr');

      var tdNom = document.createElement('td');
      tdNom.className = 'nom';
      var cle = document.createElement('span');
      cle.className = 'cle ' + s.classe;
      cle.style.background = s.classe === 'observe'
        ? 'var(--viz-ink)' : 'var(--serie-' + s.classe.slice(1) + ')';
      tdNom.appendChild(cle);
      tdNom.appendChild(document.createTextNode(s.nom));

      var tdVal = document.createElement('td');
      tdVal.className = 'valeur';
      tdVal.textContent = estPluie()
        ? (aPlu(v) ? 'pluie · ' + formatValeur(v) : 'sec')
        : formatValeur(v);

      tr.appendChild(tdNom);
      tr.appendChild(tdVal);
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    bulle.appendChild(table);

    var boite = cadre.getBoundingClientRect();
    var gauche = evt.clientX - boite.left + 16;
    if (gauche + bulle.offsetWidth > boite.width) gauche = evt.clientX - boite.left - bulle.offsetWidth - 16;
    bulle.style.left = Math.max(0, gauche) + 'px';
    bulle.style.top = Math.max(0, evt.clientY - boite.top - bulle.offsetHeight / 2) + 'px';
    bulle.dataset.visible = 'true';
  }

  /* --- Légende, tableau, plages --------------------------------------------- */

  function construireLegende() {
    legende.textContent = '';
    series().forEach(function (s) {
      var li = document.createElement('li');
      var bouton = document.createElement('button');
      bouton.type = 'button';
      bouton.setAttribute('aria-pressed', etat.masquees.has(s.nom) ? 'false' : 'true');
      var cle = document.createElement('span');
      cle.className = 'cle ' + s.classe;
      bouton.appendChild(cle);
      bouton.appendChild(document.createTextNode(s.nom));
      bouton.addEventListener('click', function () {
        if (etat.masquees.has(s.nom)) etat.masquees.delete(s.nom);
        else etat.masquees.add(s.nom);
        bouton.setAttribute('aria-pressed', etat.masquees.has(s.nom) ? 'false' : 'true');
        rendre();
      });
      li.appendChild(bouton);
      legende.appendChild(li);
    });
  }

  function majTableau() {
    var vis = visibles();
    teteTableau.textContent = '';
    var th0 = document.createElement('th');
    th0.textContent = 'Date';
    teteTableau.appendChild(th0);
    vis.forEach(function (s) {
      var th = document.createElement('th');
      th.textContent = s.nom;
      teteTableau.appendChild(th);
    });

    corpsTableau.textContent = '';
    var fragment = document.createDocumentFragment();
    for (var i = etat.debut; i <= etat.fin; i++) {
      var tr = document.createElement('tr');
      var td0 = document.createElement('td');
      td0.textContent = new Date(etat.donnees.instants[i]).toLocaleString('fr-FR', {
        day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit'
      });
      tr.appendChild(td0);
      vis.forEach(function (s) {
        var td = document.createElement('td');
        var v = s.valeurs[i];
        td.textContent = (v === null || v === undefined) ? '—' : v.toFixed(1);
        if (estPluie() && aPlu(v)) td.className = 'pluvieux';
        tr.appendChild(td);
      });
      fragment.appendChild(tr);
    }
    corpsTableau.appendChild(fragment);
  }

  function reinitialiserZoom() {
    etat.debut = 0;
    etat.fin = etat.donnees.instants.length - 1;
    rendre();
  }

  function charger(jours) {
    racine.style.opacity = '.5';
    var url = '/api/verification?station=' + encodeURIComponent(etat.station) +
      '&anticipation=' + etat.anticipation + '&jours=' + jours +
      '&variable=' + encodeURIComponent(etat.variable) +
      (etat.saison ? '&saison=' + encodeURIComponent(etat.saison) : '');
    fetch(url)
      .then(function (r) { return r.json(); })
      .then(function (d) {
        etat.donnees = d;
        etat.jours = jours;
        reinitialiserZoom();
        construireLegende();
      })
      .finally(function () { racine.style.opacity = '1'; });
  }

  racine.querySelectorAll('[data-jours]').forEach(function (bouton) {
    bouton.addEventListener('click', function () {
      racine.querySelectorAll('[data-jours]').forEach(function (b) {
        b.setAttribute('aria-pressed', b === bouton ? 'true' : 'false');
      });
      charger(parseInt(bouton.dataset.jours, 10));
    });
  });
  racine.querySelector('[data-action="reinitialiser"]').addEventListener('click', reinitialiserZoom);

  etat.donnees = JSON.parse(document.getElementById('viz-donnees').textContent);
  etat.fin = etat.donnees.instants.length - 1;
  construireLegende();
  rendre();
})();
