/* Les cinq graphes de la page climat.
 *
 * Ils vont du plus fin au plus grossier : un jour suivi à travers les années, puis
 * l'année entière superposée, puis des comptages annuels, puis la saison sans gel,
 * puis la répartition des records par décennie. Ils partagent leurs primitives de
 * tracé et rien d'autre : chacun tient son cadre et son état dans sa propre portée,
 * de sorte qu'en ajouter un sixième n'obligera à en relire aucun.
 *
 * Rien n'est calculé ici : régressions, lissages et sous-échantillonnages arrivent
 * déjà faits du serveur. Ce fichier place des pixels.
 *
 * Les couleurs vivent dans viz.css, jamais ici, pour que le mode sombre bascule sans
 * recalcul. Les rampes n'y figurent que par leurs deux bornes : le script pose une
 * position sur chaque courbe, color-mix fait le reste.
 */
(function () {
  'use strict';

  var SVGNS = 'http://www.w3.org/2000/svg';

  var MOIS = ['janvier', 'février', 'mars', 'avril', 'mai', 'juin',
              'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre'];
  var MOIS_COURTS = ['J', 'F', 'M', 'A', 'M', 'J', 'J', 'A', 'S', 'O', 'N', 'D'];

  /* Abrégés à la main : tronquer à trois lettres donnerait « jui » pour juin comme
     pour juillet, et l'axe deviendrait faux au beau milieu de l'été. */
  var MOIS_ABREGES = ['jan', 'fév', 'mar', 'avr', 'mai', 'juin',
                      'juil', 'août', 'sep', 'oct', 'nov', 'déc'];

  function el(nom, attrs) {
    var n = document.createElementNS(SVGNS, nom);
    for (var k in attrs) n.setAttribute(k, attrs[k]);
    return n;
  }

  function json(id) {
    var source = document.getElementById(id);
    return source ? JSON.parse(source.textContent) : null;
  }

  /* Graduations : un pas rond, jamais plus d'une dizaine de repères. Un axe chargé
     se lit moins bien qu'un axe clairsemé. */
  function pas(etendue, cible) {
    var brut = etendue / cible;
    var magnitude = Math.pow(10, Math.floor(Math.log(brut) / Math.LN10));
    var reste = brut / magnitude;
    var facteur = reste >= 5 ? 5 : reste >= 2 ? 2 : 1;
    return facteur * magnitude;
  }

  function graduations(bas, haut, cible) {
    var p = pas(haut - bas, cible);
    var valeurs = [];
    for (var v = Math.ceil(bas / p) * p; v <= haut; v += p) valeurs.push(Math.round(v * 100) / 100);
    return valeurs;
  }

  function chemin(points) {
    return points.map(function (p, i) {
      return (i ? 'L' : 'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1);
    }).join(' ');
  }

  /* Le SVG est mis à l'échelle par le navigateur : sur un écran étroit, un cadre de
     900 unités réduit la typographie des graduations à quelques pixels. On rétrécit
     donc le cadre lui-même plutôt que de laisser rapetisser son contenu. */
  function cadrage(cadre, hauteurLarge, hauteurEtroite) {
    var place = (cadre && cadre.clientWidth) || 900;
    var etroit = place < 620;
    return {
      etroit: etroit,
      largeur: etroit ? 480 : 900,
      hauteur: etroit ? hauteurEtroite : hauteurLarge,
      marges: etroit
        ? { gauche: 34, droite: 10, haut: 14, bas: 28 }
        : { gauche: 46, droite: 16, haut: 16, bas: 34 }
    };
  }

  /* Redessine au franchissement du seuil, pas à chaque pixel : redessiner en continu
     pendant qu'on redimensionne coûterait cher pour rien. */
  function surRedimensionnement(etat, rendre) {
    var attente = null;
    window.addEventListener('resize', function () {
      if (attente) clearTimeout(attente);
      attente = setTimeout(function () {
        var avant = etat.etroit;
        if (cadrage(etat.cadre, 1, 1).etroit !== avant) rendre();
      }, 150);
    });
  }

  function placerBulle(racine, bulle, evt) {
    var boite = racine.getBoundingClientRect();
    var x = evt.clientX - boite.left + 14;
    bulle.style.left = Math.min(x, boite.width - bulle.offsetWidth - 8) + 'px';
    bulle.style.top = Math.max(0, evt.clientY - boite.top - bulle.offsetHeight - 12) + 'px';
  }

  // ---------------------------------------------------------------------------
  // Graphe 1 : un jour de l'année, année après année.
  // ---------------------------------------------------------------------------
  function grapheTendance() {
    var racine = document.querySelector('[data-climat]');
    var donnees = json('climat-donnees');
    if (!racine || !donnees) return;

    var cadre = racine.querySelector('.viz-cadre');
    var legende = racine.querySelector('.viz-legende');
    var bulle = racine.querySelector('.viz-bulle');
    var masquees = new Set();
    var etat = { cadre: cadre, etroit: false };

    function visibles() {
      return donnees.series.filter(function (s) { return !masquees.has(s.cle); });
    }

    /* L'axe des années part du premier point mesuré et va jusqu'à l'horizon, même si
       aucune série n'a de tendance : la page a annoncé un prolongement, l'axe doit le
       montrer, fût-il vide. */
    function bornes() {
      var annees = [], temperatures = [];
      visibles().forEach(function (s) {
        s.points.forEach(function (p) { annees.push(p.annee); temperatures.push(p.valeur); });
        if (s.tendance) {
          s.tendance.courbe.forEach(function (c) {
            annees.push(c.annee);
            temperatures.push(c.bas, c.haut);
          });
        }
      });
      if (!annees.length) return null;
      var tmin = Math.min.apply(null, temperatures);
      var tmax = Math.max.apply(null, temperatures);
      var marge = Math.max(0.5, (tmax - tmin) * 0.06);
      return {
        x0: Math.min.apply(null, annees), x1: Math.max.apply(null, annees),
        y0: tmin - marge, y1: tmax + marge
      };
    }

    function rendre() {
      var c = cadrage(cadre, 380, 320);
      etat.etroit = c.etroit;
      cadre.textContent = '';

      var b = bornes();
      if (!b) {
        var vide = document.createElement('p');
        vide.className = 'viz-vide';
        vide.textContent = 'Aucune série affichée.';
        cadre.appendChild(vide);
        return;
      }

      var M = c.marges;
      var largeurTrace = c.largeur - M.gauche - M.droite;
      var hauteurTrace = c.hauteur - M.haut - M.bas;
      function x(annee) { return M.gauche + (annee - b.x0) / (b.x1 - b.x0) * largeurTrace; }
      function y(t) { return M.haut + (b.y1 - t) / (b.y1 - b.y0) * hauteurTrace; }

      var svg = el('svg', {
        viewBox: '0 0 ' + c.largeur + ' ' + c.hauteur,
        preserveAspectRatio: 'xMidYMid meet', role: 'img'
      });
      svg.setAttribute('aria-label',
        'Températures du jour choisi, année après année, avec la tendance ajustée.');

      graduations(b.y0, b.y1, c.etroit ? 4 : 6).forEach(function (t) {
        svg.appendChild(el('line', {
          x1: M.gauche, x2: c.largeur - M.droite, y1: y(t), y2: y(t), class: 'viz-grille-ligne'
        }));
        var texte = el('text', { x: M.gauche - 8, y: y(t) + 4, class: 'viz-graduation y' });
        texte.textContent = t + '°';
        svg.appendChild(texte);
      });

      graduations(b.x0, b.x1, c.etroit ? 4 : 8).forEach(function (annee) {
        if (annee < b.x0 || annee > b.x1) return;
        var texte = el('text', {
          x: x(annee), y: c.hauteur - M.bas + 18, class: 'viz-graduation x'
        });
        texte.textContent = annee;
        svg.appendChild(texte);
      });
      svg.appendChild(el('line', {
        x1: M.gauche, x2: c.largeur - M.droite,
        y1: c.hauteur - M.bas, y2: c.hauteur - M.bas, class: 'viz-axe-ligne'
      }));

      var derniere = donnees.derniere_annee_mesuree;
      if (derniere && derniere < b.x1) {
        svg.appendChild(el('line', {
          x1: x(derniere), x2: x(derniere), y1: M.haut, y2: c.hauteur - M.bas,
          class: 'climat-frontiere'
        }));
        var mention = el('text', {
          x: x(derniere) + 6, y: M.haut + 12, class: 'climat-frontiere-texte'
        });
        mention.textContent = 'prolongement';
        svg.appendChild(mention);
      }

      var couche = el('g', {});

      // 1. Les bandes d'incertitude, tout au fond.
      visibles().forEach(function (s) {
        if (!s.tendance) return;
        var haut = s.tendance.courbe.map(function (p) { return [x(p.annee), y(p.haut)]; });
        var bas = s.tendance.courbe.map(function (p) { return [x(p.annee), y(p.bas)]; }).reverse();
        couche.appendChild(el('path', {
          d: chemin(haut.concat(bas)) + ' Z', class: 'climat-bande ' + s.cle
        }));
      });

      // 2. Les droites : trait plein sur le mesuré, tireté au-delà.
      visibles().forEach(function (s) {
        if (!s.tendance) return;
        [['', function (p) { return p.annee <= derniere; }],
         [' prolongee', function (p) { return p.annee >= derniere; }]].forEach(function (part) {
          var points = s.tendance.courbe.filter(part[1]);
          if (points.length < 2) return;
          couche.appendChild(el('path', {
            d: chemin(points.map(function (p) { return [x(p.annee), y(p.valeur)]; })),
            class: 'climat-droite ' + s.cle + part[0]
          }));
        });
      });

      // 3. Le nuage des années mesurées, au premier plan : la droite ne doit jamais
      //    masquer ce qu'elle résume.
      visibles().forEach(function (s) {
        s.points.forEach(function (p) {
          couche.appendChild(el('circle', {
            cx: x(p.annee), cy: y(p.valeur), r: 3, class: 'climat-point ' + s.cle
          }));
        });
      });

      svg.appendChild(couche);
      var survol = el('g', {});
      svg.appendChild(survol);
      cadre.appendChild(svg);

      svg.addEventListener('pointermove', function (evt) {
        var boite = svg.getBoundingClientRect();
        var ratio = (evt.clientX - boite.left) / boite.width * c.largeur;
        var brute = b.x0 + (ratio - M.gauche) / largeurTrace * (b.x1 - b.x0);
        var annee = Math.min(b.x1, Math.max(b.x0, Math.round(brute)));

        survol.textContent = '';
        survol.appendChild(el('line', {
          x1: x(annee), x2: x(annee), y1: M.haut, y2: c.hauteur - M.bas, class: 'climat-curseur'
        }));

        var lignes = [];
        visibles().forEach(function (s) {
          var point = s.points.find(function (p) { return p.annee === annee; });
          if (point) {
            survol.appendChild(el('circle', {
              cx: x(annee), cy: y(point.valeur), r: 5, class: 'climat-halo'
            }));
            survol.appendChild(el('circle', {
              cx: x(annee), cy: y(point.valeur), r: 3.5,
              class: 'climat-point ' + s.cle, style: 'opacity:1'
            }));
          }
          var ajustee = s.tendance
            ? s.tendance.courbe.find(function (p) { return p.annee === annee; })
            : null;
          lignes.push({
            cle: s.cle, nom: s.nom,
            mesure: point ? point.valeur.toFixed(1) + ' °C' : '—',
            second: ajustee ? ajustee.valeur.toFixed(1) + ' °C' : '—'
          });
        });

        var mesuree = derniere && annee <= derniere;
        remplirBulle(racine, bulle, annee + (mesuree ? '' : ' — prolongé'), lignes);
        placerBulle(racine, bulle, evt);
      });

      svg.addEventListener('pointerleave', function () {
        survol.textContent = '';
        bulle.dataset.visible = 'false';
      });
    }

    donnees.series.forEach(function (s) {
      var pente = s.tendance
        ? (s.tendance.pente_par_decennie >= 0 ? '+' : '')
          + s.tendance.pente_par_decennie.toFixed(2) + ' °C/décennie'
          + (s.tendance.significative ? '' : ' (non significative)')
        : 'pas assez d’années pour une tendance';
      ajouterLegende(legende, s.cle, s.nom, pente, '', function () {
        if (masquees.has(s.cle)) masquees.delete(s.cle); else masquees.add(s.cle);
        rendre();
        return !masquees.has(s.cle);
      });
    });

    rendre();
    surRedimensionnement(etat, rendre);
  }

  // ---------------------------------------------------------------------------
  // Graphe 2 : toutes les années superposées sur l'axe des quantièmes.
  // ---------------------------------------------------------------------------
  function grapheCycle() {
    var racine = document.querySelector('[data-cycle]');
    var donnees = json('cycle-donnees');
    if (!racine || !donnees || !donnees.annees.length) return;

    var cadre = racine.querySelector('.viz-cadre');
    var legende = racine.querySelector('.viz-legende');
    var bulle = racine.querySelector('.viz-bulle');
    var masquees = new Set();
    var etat = { cadre: cadre, etroit: false };

    var reperes = donnees.decennies;
    var courante = reperes[0];
    var parAnnee = {};
    donnees.annees.forEach(function (a) { parAnnee[a.annee] = a; });

    /* Position dans la rampe : 0 pour la plus ancienne décennie, 1 pour l'année en
       cours. Seule cette position vient de la donnée — les deux teintes sont en CSS. */
    function age(annee) {
      var plus_ancienne = reperes[reperes.length - 1];
      return courante === plus_ancienne ? 1 : (annee - plus_ancienne) / (courante - plus_ancienne);
    }

    function dateDe(q) {
      // Année de référence non bissextile : l'axe est calé sur 365 jours.
      var d = new Date(Date.UTC(2001, 0, q));
      return d.getUTCDate() + ' ' + MOIS[d.getUTCMonth()];
    }

    function visibles() {
      return reperes.filter(function (a) { return !masquees.has(a); });
    }

    function bornes() {
      var basses = [], hautes = [];
      donnees.annees.forEach(function (a) {
        a.valeurs.forEach(function (v) { basses.push(v); hautes.push(v); });
      });
      var tmin = Math.min.apply(null, basses);
      var tmax = Math.max.apply(null, hautes);
      var marge = Math.max(0.5, (tmax - tmin) * 0.05);
      return { y0: tmin - marge, y1: tmax + marge };
    }

    function rendre() {
      var c = cadrage(cadre, 420, 340);
      etat.etroit = c.etroit;
      cadre.textContent = '';

      var b = bornes();
      var M = c.marges;
      var largeurTrace = c.largeur - M.gauche - M.droite;
      var hauteurTrace = c.hauteur - M.haut - M.bas;
      function x(q) { return M.gauche + (q - 1) / (donnees.jours_an - 1) * largeurTrace; }
      function y(t) { return M.haut + (b.y1 - t) / (b.y1 - b.y0) * hauteurTrace; }

      var svg = el('svg', {
        viewBox: '0 0 ' + c.largeur + ' ' + c.hauteur,
        preserveAspectRatio: 'xMidYMid meet', role: 'img'
      });
      svg.setAttribute('aria-label',
        'Température moyenne lissée au fil de l’année, une courbe par année, '
        + 'les décennies mises en avant.');

      graduations(b.y0, b.y1, c.etroit ? 4 : 6).forEach(function (t) {
        svg.appendChild(el('line', {
          x1: M.gauche, x2: c.largeur - M.droite, y1: y(t), y2: y(t), class: 'viz-grille-ligne'
        }));
        var texte = el('text', { x: M.gauche - 8, y: y(t) + 4, class: 'viz-graduation y' });
        texte.textContent = t + '°';
        svg.appendChild(texte);
      });

      // Axe des mois : le repère naturel d'une année, là où un quantième ne dit rien.
      donnees.debuts_de_mois.forEach(function (debut, i) {
        var suivant = donnees.debuts_de_mois[i + 1] || donnees.jours_an + 1;
        var texte = el('text', {
          x: x((debut + suivant) / 2), y: c.hauteur - M.bas + 18, class: 'viz-graduation x'
        });
        texte.textContent = c.etroit ? MOIS_COURTS[i] : MOIS_ABREGES[i];
        svg.appendChild(texte);
        if (i) {
          svg.appendChild(el('line', {
            x1: x(debut), x2: x(debut), y1: M.haut, y2: c.hauteur - M.bas,
            class: 'viz-grille-ligne'
          }));
        }
      });
      svg.appendChild(el('line', {
        x1: M.gauche, x2: c.largeur - M.droite,
        y1: c.hauteur - M.bas, y2: c.hauteur - M.bas, class: 'viz-axe-ligne'
      }));

      function tracer(a) {
        return chemin(a.quantiemes.map(function (q, i) { return [x(q), y(a.valeurs[i])]; }));
      }

      // 1. Toutes les années, presque effacées : c'est leur épaisseur collective qui
      //    montre ce qu'une année peut faire, et sans elle les décennies sembleraient
      //    se succéder régulièrement.
      var fond = el('g', {});
      var mis_en_avant = new Set(visibles());
      donnees.annees.forEach(function (a) {
        if (mis_en_avant.has(a.annee)) return;
        fond.appendChild(el('path', { d: tracer(a), class: 'cycle-annee' }));
      });
      svg.appendChild(fond);

      // 2. Les décennies, de la plus ancienne à la plus récente pour que l'année en
      //    cours passe au-dessus.
      var avant = el('g', {});
      visibles().slice().reverse().forEach(function (annee) {
        var a = parAnnee[annee];
        if (!a) return;
        avant.appendChild(el('path', {
          d: tracer(a),
          class: 'cycle-repere' + (annee === courante ? ' courante' : ''),
          style: '--age:' + age(annee).toFixed(3)
        }));
      });
      svg.appendChild(avant);

      // 3. L'année en cours porte son millésime en bout de courbe : le seul repère
      //    qu'on lit sans revenir à la légende.
      var actuelle = parAnnee[courante];
      if (actuelle && !masquees.has(courante)) {
        var dernier = actuelle.quantiemes.length - 1;
        var etiquette = el('text', {
          x: Math.min(x(actuelle.quantiemes[dernier]) + 6, c.largeur - M.droite - 30),
          y: y(actuelle.valeurs[dernier]) - 6,
          class: 'cycle-etiquette'
        });
        etiquette.textContent = courante;
        svg.appendChild(etiquette);
      }

      // Le jour choisi en haut de page, reporté ici : les deux graphes parlent du
      // même lieu, autant qu'ils parlent visiblement du même moment.
      if (donnees.quantieme_choisi) {
        var q = donnees.quantieme_choisi;
        svg.appendChild(el('line', {
          x1: x(q), x2: x(q), y1: M.haut, y2: c.hauteur - M.bas, class: 'cycle-jour-choisi'
        }));
        // Au pied du graphe et non en tête : la courbe de l'année en cours s'arrête
        // toujours près de la date du jour, et son millésime occupe déjà le haut.
        var jour = el('text', {
          x: Math.min(x(q) + 5, c.largeur - M.droite - 54), y: c.hauteur - M.bas - 7,
          class: 'cycle-jour-texte'
        });
        jour.textContent = dateDe(q);
        svg.appendChild(jour);
      }

      var survol = el('g', {});
      svg.appendChild(survol);
      cadre.appendChild(svg);

      svg.addEventListener('pointermove', function (evt) {
        var boite = svg.getBoundingClientRect();
        var ratio = (evt.clientX - boite.left) / boite.width * c.largeur;
        var brut = 1 + (ratio - M.gauche) / largeurTrace * (donnees.jours_an - 1);
        var q = Math.min(donnees.jours_an, Math.max(1, Math.round(brut)));

        survol.textContent = '';
        survol.appendChild(el('line', {
          x1: x(q), x2: x(q), y1: M.haut, y2: c.hauteur - M.bas, class: 'climat-curseur'
        }));

        var lignes = [];
        visibles().forEach(function (annee) {
          var a = parAnnee[annee];
          if (!a) return;
          // Le point le plus proche : les courbes sont échantillonnées tous les cinq
          // jours, il n'y a pas de valeur à chaque quantième.
          var meilleur = -1, ecart = Infinity;
          a.quantiemes.forEach(function (qi, i) {
            var d = Math.abs(qi - q);
            if (d < ecart) { ecart = d; meilleur = i; }
          });
          if (meilleur < 0 || ecart > donnees.pas_j) return;
          survol.appendChild(el('circle', {
            cx: x(a.quantiemes[meilleur]), cy: y(a.valeurs[meilleur]), r: 3.5,
            class: 'climat-halo'
          }));
          lignes.push({
            cle: 'decennie', age: age(annee), nom: String(annee),
            mesure: a.valeurs[meilleur].toFixed(1) + ' °C', second: ''
          });
        });

        remplirBulle(racine, bulle, dateDe(q), lignes);
        placerBulle(racine, bulle, evt);
      });

      svg.addEventListener('pointerleave', function () {
        survol.textContent = '';
        bulle.dataset.visible = 'false';
      });
    }

    reperes.forEach(function (annee) {
      var a = parAnnee[annee];
      var detail = a && !a.complete ? 'année partielle' : '';
      ajouterLegende(legende, 'decennie', String(annee), detail,
        '--age:' + age(annee).toFixed(3), function () {
          if (masquees.has(annee)) masquees.delete(annee); else masquees.add(annee);
          rendre();
          return !masquees.has(annee);
        });
    });

    rendre();
    surRedimensionnement(etat, rendre);
  }

  function ajouterLegende(legende, cle, nom, detail, style, basculer) {
    var item = document.createElement('li');
    var bouton = document.createElement('button');
    bouton.type = 'button';
    bouton.setAttribute('aria-pressed', 'true');
    bouton.innerHTML = '<span class="cle ' + cle + '"' + (style ? ' style="' + style + '"' : '')
      + '></span>' + nom + (detail ? ' <span class="nom">— ' + detail + '</span>' : '');
    bouton.addEventListener('click', function () {
      bouton.setAttribute('aria-pressed', basculer() ? 'true' : 'false');
    });
    item.appendChild(bouton);
    legende.appendChild(item);
  }

  function remplirBulle(racine, bulle, titre, lignes) {
    var html = '<p class="titre">' + titre + '</p><table><tbody>';
    lignes.forEach(function (l) {
      var style = l.age === undefined ? '' : ' style="--age:' + l.age.toFixed(3) + '"';
      html += '<tr><td><span class="cle ' + l.cle + '"' + style + '></span>' + l.nom + '</td>'
        + '<td class="valeur">' + l.mesure + '</td>'
        + (l.second ? '<td class="nom">' + l.second + '</td>' : '') + '</tr>';
    });
    bulle.innerHTML = html + '</tbody></table>';
    bulle.dataset.visible = 'true';
  }

  // ---------------------------------------------------------------------------
  // Graphe 3 : combien de jours par an franchissent un seuil.
  // ---------------------------------------------------------------------------
  function grapheSeuils() {
    var racine = document.querySelector('[data-seuils]');
    var donnees = json('seuils-donnees');
    if (!racine || !donnees || !donnees.seuils.length) return;

    var cadre = racine.querySelector('.viz-cadre');
    var legende = racine.querySelector('.viz-legende');
    var bulle = racine.querySelector('.viz-bulle');
    var masquees = new Set();
    var etat = { cadre: cadre, etroit: false };

    function visibles() {
      return donnees.seuils.filter(function (s) { return !masquees.has(s.cle); });
    }

    function bornes() {
      var annees = [], jours = [0];
      visibles().forEach(function (s) {
        s.points.forEach(function (p) { annees.push(p.annee); jours.push(p.jours); });
      });
      if (!annees.length) return null;
      return {
        x0: Math.min.apply(null, annees), x1: Math.max.apply(null, annees),
        y0: 0, y1: Math.max.apply(null, jours) * 1.06
      };
    }

    function rendre() {
      var c = cadrage(cadre, 380, 320);
      etat.etroit = c.etroit;
      cadre.textContent = '';

      var b = bornes();
      if (!b) {
        var vide = document.createElement('p');
        vide.className = 'viz-vide';
        vide.textContent = 'Aucun seuil affiché.';
        cadre.appendChild(vide);
        return;
      }

      var M = c.marges;
      var largeurTrace = c.largeur - M.gauche - M.droite;
      var hauteurTrace = c.hauteur - M.haut - M.bas;
      function x(a) { return M.gauche + (a - b.x0) / (b.x1 - b.x0) * largeurTrace; }
      function y(v) { return M.haut + (b.y1 - v) / (b.y1 - b.y0) * hauteurTrace; }

      var svg = el('svg', {
        viewBox: '0 0 ' + c.largeur + ' ' + c.hauteur,
        preserveAspectRatio: 'xMidYMid meet', role: 'img'
      });
      svg.setAttribute('aria-label',
        'Nombre de jours par an franchissant chaque seuil de température.');

      graduations(b.y0, b.y1, c.etroit ? 4 : 6).forEach(function (v) {
        svg.appendChild(el('line', {
          x1: M.gauche, x2: c.largeur - M.droite, y1: y(v), y2: y(v), class: 'viz-grille-ligne'
        }));
        var t = el('text', { x: M.gauche - 8, y: y(v) + 4, class: 'viz-graduation y' });
        t.textContent = v;
        svg.appendChild(t);
      });

      graduations(b.x0, b.x1, c.etroit ? 4 : 8).forEach(function (a) {
        if (a < b.x0 || a > b.x1) return;
        var t = el('text', { x: x(a), y: c.hauteur - M.bas + 18, class: 'viz-graduation x' });
        t.textContent = a;
        svg.appendChild(t);
      });
      svg.appendChild(el('line', {
        x1: M.gauche, x2: c.largeur - M.droite,
        y1: c.hauteur - M.bas, y2: c.hauteur - M.bas, class: 'viz-axe-ligne'
      }));

      // Le trait fin porte les années réelles, le trait épais la droite ajustée.
      // Cacher les années derrière la seule droite masquerait leur variabilité,
      // qui est précisément ce qui rend la pente remarquable.
      visibles().forEach(function (s) {
        svg.appendChild(el('path', {
          d: chemin(s.points.map(function (p) { return [x(p.annee), y(p.jours)]; })),
          class: 'seuil-serie ' + s.cle
        }));
      });
      visibles().forEach(function (s) {
        if (!s.tendance) return;
        svg.appendChild(el('path', {
          d: chemin(s.tendance.courbe.map(function (p) { return [x(p.annee), y(p.valeur)]; })),
          class: 'seuil-droite ' + s.cle
        }));
      });

      var survol = el('g', {});
      svg.appendChild(survol);
      cadre.appendChild(svg);

      svg.addEventListener('pointermove', function (evt) {
        var boite = svg.getBoundingClientRect();
        var ratio = (evt.clientX - boite.left) / boite.width * c.largeur;
        var annee = Math.round(b.x0 + (ratio - M.gauche) / largeurTrace * (b.x1 - b.x0));
        annee = Math.min(b.x1, Math.max(b.x0, annee));

        survol.textContent = '';
        survol.appendChild(el('line', {
          x1: x(annee), x2: x(annee), y1: M.haut, y2: c.hauteur - M.bas, class: 'climat-curseur'
        }));

        var lignes = [];
        visibles().forEach(function (s) {
          var point = s.points.find(function (p) { return p.annee === annee; });
          if (!point) return;
          survol.appendChild(el('circle', {
            cx: x(annee), cy: y(point.jours), r: 4.5, class: 'climat-halo'
          }));
          survol.appendChild(el('circle', {
            cx: x(annee), cy: y(point.jours), r: 3, class: 'seuil-point ' + s.cle
          }));
          lignes.push({ cle: s.cle, nom: s.nom, mesure: point.jours + ' j', second: '' });
        });
        remplirBulle(racine, bulle, String(annee), lignes);
        placerBulle(racine, bulle, evt);
      });

      svg.addEventListener('pointerleave', function () {
        survol.textContent = '';
        bulle.dataset.visible = 'false';
      });
    }

    donnees.seuils.forEach(function (s) {
      var detail = s.tendance
        ? (s.tendance.pente_par_decennie >= 0 ? '+' : '')
          + s.tendance.pente_par_decennie.toFixed(1) + ' j/décennie'
          + (s.tendance.significative ? '' : ' (non significative)')
        : 'pas assez d’années';
      ajouterLegende(legende, s.cle, s.nom, detail, '', function () {
        if (masquees.has(s.cle)) masquees.delete(s.cle); else masquees.add(s.cle);
        rendre();
        return !masquees.has(s.cle);
      });
    });

    rendre();
    surRedimensionnement(etat, rendre);
  }

  // ---------------------------------------------------------------------------
  // Graphe 4 : la saison sans gel, une ligne par année.
  // ---------------------------------------------------------------------------
  function grapheGel() {
    var racine = document.querySelector('[data-gel]');
    var donnees = json('gel-donnees');
    if (!racine || !donnees || !donnees.saisons.length) return;

    var cadre = racine.querySelector('.viz-cadre');
    var bulle = racine.querySelector('.viz-bulle');
    var etat = { cadre: cadre, etroit: false };

    function dateDe(q) {
      var d = new Date(Date.UTC(2001, 0, q));
      return d.getUTCDate() + ' ' + MOIS[d.getUTCMonth()];
    }

    function rendre() {
      // Une hauteur proportionnelle au nombre d'années : cent dix lignes dans
      // trois cents pixels seraient illisibles, et une hauteur fixe écraserait
      // les postes centenaires autant qu'elle étirerait les jeunes.
      var lignes = donnees.saisons.length;
      var c = cadrage(cadre, Math.max(240, Math.min(560, lignes * 4 + 60)),
                             Math.max(220, Math.min(460, lignes * 3 + 50)));
      etat.etroit = c.etroit;
      cadre.textContent = '';

      var M = c.marges;
      var largeurTrace = c.largeur - M.gauche - M.droite;
      var hauteurTrace = c.hauteur - M.haut - M.bas;
      var pasLigne = hauteurTrace / lignes;
      function x(q) { return M.gauche + (q - 1) / (donnees.jours_an - 1) * largeurTrace; }
      function y(i) { return M.haut + i * pasLigne; }

      var svg = el('svg', {
        viewBox: '0 0 ' + c.largeur + ' ' + c.hauteur,
        preserveAspectRatio: 'xMidYMid meet', role: 'img'
      });
      svg.setAttribute('aria-label',
        'Périodes de gel possible chaque année ; le chenal libre au milieu est la '
        + 'saison sans gel, et il s’élargit.');

      donnees.debuts_de_mois.forEach(function (debut, i) {
        var suivant = donnees.debuts_de_mois[i + 1] || donnees.jours_an + 1;
        var t = el('text', {
          x: x((debut + suivant) / 2), y: c.hauteur - M.bas + 18, class: 'viz-graduation x'
        });
        t.textContent = c.etroit ? MOIS_COURTS[i] : MOIS_ABREGES[i];
        svg.appendChild(t);
        if (i) {
          svg.appendChild(el('line', {
            x1: x(debut), x2: x(debut), y1: M.haut, y2: c.hauteur - M.bas,
            class: 'viz-grille-ligne'
          }));
        }
      });

      var hauteurBarre = Math.max(1.5, pasLigne - 0.8);
      donnees.saisons.forEach(function (s, i) {
        svg.appendChild(el('rect', {
          x: M.gauche, y: y(i), width: Math.max(0, x(s.dernier_gel) - M.gauche),
          height: hauteurBarre, class: 'gel-segment'
        }));
        svg.appendChild(el('rect', {
          x: x(s.premier_gel), y: y(i),
          width: Math.max(0, c.largeur - M.droite - x(s.premier_gel)),
          height: hauteurBarre, class: 'gel-segment'
        }));
        if (s.annee % 10 === 0) {
          svg.appendChild(el('line', {
            x1: M.gauche - 4, x2: M.gauche, y1: y(i) + hauteurBarre / 2,
            y2: y(i) + hauteurBarre / 2, class: 'gel-decennie'
          }));
          var t = el('text', {
            x: M.gauche - 7, y: y(i) + hauteurBarre / 2 + 3, class: 'gel-annee-texte',
            'text-anchor': 'end'
          });
          t.textContent = s.annee;
          svg.appendChild(t);
        }
      });

      var survol = el('g', {});
      svg.appendChild(survol);
      cadre.appendChild(svg);

      svg.addEventListener('pointermove', function (evt) {
        var boite = svg.getBoundingClientRect();
        var haut = (evt.clientY - boite.top) / boite.height * c.hauteur;
        var i = Math.floor((haut - M.haut) / pasLigne);
        survol.textContent = '';
        if (i < 0 || i >= lignes) { bulle.dataset.visible = 'false'; return; }
        var s = donnees.saisons[i];
        survol.appendChild(el('rect', {
          x: M.gauche, y: y(i) - 1, width: largeurTrace, height: hauteurBarre + 2,
          fill: 'none', stroke: 'currentColor', 'stroke-width': 1, opacity: .35
        }));
        remplirBulle(racine, bulle, String(s.annee), [
          { cle: 'froid', nom: 'Dernier gel', mesure: dateDe(s.dernier_gel), second: '' },
          { cle: 'froid', nom: 'Premier gel', mesure: dateDe(s.premier_gel), second: '' },
          { cle: 'froid', nom: 'Sans gel', mesure: s.duree + ' j', second: '' }
        ]);
        placerBulle(racine, bulle, evt);
      });

      svg.addEventListener('pointerleave', function () {
        survol.textContent = '';
        bulle.dataset.visible = 'false';
      });
    }

    rendre();
    surRedimensionnement(etat, rendre);
  }

  // ---------------------------------------------------------------------------
  // Graphe 5 : qui détient les records, rapporté à ce qu'un climat stable donnerait.
  // ---------------------------------------------------------------------------
  function grapheRecords() {
    var racine = document.querySelector('[data-records]');
    var donnees = json('records-donnees');
    if (!racine || !donnees || !donnees.decennies.length) return;

    var cadre = racine.querySelector('.viz-cadre');
    var legende = racine.querySelector('.viz-legende');
    var bulle = racine.querySelector('.viz-bulle');
    var masquees = new Set();
    var etat = { cadre: cadre, etroit: false };
    var SERIES = [{ cle: 'chaleur', nom: 'Records de chaleur' },
                  { cle: 'froid', nom: 'Records de froid' }];

    function visibles() {
      return SERIES.filter(function (s) { return !masquees.has(s.cle); });
    }

    function rendre() {
      var c = cadrage(cadre, 340, 300);
      etat.etroit = c.etroit;
      cadre.textContent = '';

      var hautes = [1.2];
      donnees.decennies.forEach(function (d) {
        visibles().forEach(function (s) {
          if (d[s.cle]) hautes.push(d[s.cle].indice, 1 + d[s.cle].bruit);
        });
      });
      var y1 = Math.max.apply(null, hautes) * 1.08;

      var M = c.marges;
      var largeurTrace = c.largeur - M.gauche - M.droite;
      var hauteurTrace = c.hauteur - M.haut - M.bas;
      var pasDec = largeurTrace / donnees.decennies.length;
      function y(v) { return M.haut + (y1 - v) / y1 * hauteurTrace; }

      var svg = el('svg', {
        viewBox: '0 0 ' + c.largeur + ' ' + c.hauteur,
        preserveAspectRatio: 'xMidYMid meet', role: 'img'
      });
      svg.setAttribute('aria-label',
        'Part des records détenue par chaque décennie, rapportée à ce qu’un climat '
        + 'stable produirait.');

      graduations(0, y1, c.etroit ? 3 : 5).forEach(function (v) {
        svg.appendChild(el('line', {
          x1: M.gauche, x2: c.largeur - M.droite, y1: y(v), y2: y(v), class: 'viz-grille-ligne'
        }));
        var t = el('text', { x: M.gauche - 8, y: y(v) + 4, class: 'viz-graduation y' });
        t.textContent = v.toFixed(v % 1 ? 1 : 0);
        svg.appendChild(t);
      });

      // La bande de bruit, décennie par décennie : sa largeur dépend du nombre
      // d'années apportées, elle est donc plus lâche aux extrémités de la série.
      donnees.decennies.forEach(function (d, i) {
        var bruit = Math.max(
          d.chaleur ? d.chaleur.bruit : 0, d.froid ? d.froid.bruit : 0
        );
        if (!bruit) return;
        svg.appendChild(el('rect', {
          x: M.gauche + i * pasDec, y: y(1 + bruit),
          width: pasDec, height: Math.max(0, y(1 - bruit) - y(1 + bruit)),
          class: 'records-bruit'
        }));
      });

      svg.appendChild(el('line', {
        x1: M.gauche, x2: c.largeur - M.droite, y1: y(1), y2: y(1),
        class: 'records-reference'
      }));
      // Pas d'étiquette flottante sur cette ligne : quelle que soit sa position, une
      // barre finit par passer dessous. La graduation « 1 » de l'axe et le chapeau du
      // graphe disent déjà ce qu'elle vaut.

      var vues = visibles();
      var largeurBarre = Math.min(18, (pasDec - 6) / Math.max(1, vues.length));
      donnees.decennies.forEach(function (d, i) {
        var centre = M.gauche + (i + 0.5) * pasDec;
        vues.forEach(function (s, k) {
          var part = d[s.cle];
          if (!part) return;
          var gauche = centre - (vues.length * largeurBarre) / 2 + k * largeurBarre;
          svg.appendChild(el('rect', {
            x: gauche + 1, y: y(part.indice), width: Math.max(1, largeurBarre - 2),
            height: Math.max(0, y(0) - y(part.indice)), class: 'record-barre ' + s.cle
          }));
        });
        if (!c.etroit || i % 2 === 0) {
          var t = el('text', {
            x: centre, y: c.hauteur - M.bas + 18, class: 'viz-graduation x'
          });
          t.textContent = d.decennie;
          svg.appendChild(t);
        }
      });

      svg.appendChild(el('line', {
        x1: M.gauche, x2: c.largeur - M.droite,
        y1: c.hauteur - M.bas, y2: c.hauteur - M.bas, class: 'viz-axe-ligne'
      }));

      cadre.appendChild(svg);

      svg.addEventListener('pointermove', function (evt) {
        var boite = svg.getBoundingClientRect();
        var ratio = (evt.clientX - boite.left) / boite.width * c.largeur;
        var i = Math.floor((ratio - M.gauche) / pasDec);
        if (i < 0 || i >= donnees.decennies.length) { bulle.dataset.visible = 'false'; return; }
        var d = donnees.decennies[i];
        var lignes = vues.filter(function (s) { return d[s.cle]; }).map(function (s) {
          return {
            cle: s.cle, nom: s.nom,
            mesure: d[s.cle].indice.toFixed(2),
            second: d[s.cle].records + ' / ' + d[s.cle].attendus
          };
        });
        remplirBulle(racine, bulle, d.decennie + 's — ' + d.annees + ' années', lignes);
        placerBulle(racine, bulle, evt);
      });

      svg.addEventListener('pointerleave', function () { bulle.dataset.visible = 'false'; });
    }

    SERIES.forEach(function (s) {
      ajouterLegende(legende, s.cle, s.nom, '', '', function () {
        if (masquees.has(s.cle)) masquees.delete(s.cle); else masquees.add(s.cle);
        rendre();
        return !masquees.has(s.cle);
      });
    });

    rendre();
    surRedimensionnement(etat, rendre);
  }

  // ---------------------------------------------------------------------------
  // Graphe 6 : ce que l'été reçoit face à ce qu'il réclame.
  // ---------------------------------------------------------------------------
  function grapheBilan() {
    var racine = document.querySelector('[data-bilan]');
    var donnees = json('bilan-donnees');
    if (!racine || !donnees || !donnees.saisons.length) return;

    var cadre = racine.querySelector('.viz-cadre');
    var legende = racine.querySelector('.viz-legende');
    var bulle = racine.querySelector('.viz-bulle');
    var etat = { cadre: cadre, etroit: false };
    var saisons = donnees.saisons;

    /* La bande entre les deux courbes change de sens quand elles se croisent. On
       découpe donc intervalle par intervalle, en coupant au point de croisement :
       une bande d'une seule teinte laisserait croire au déficit permanent, ou à
       l'excédent, selon la couleur choisie. */
    function bandes(x, y) {
      var polygones = [];
      for (var i = 0; i < saisons.length - 1; i++) {
        var g = saisons[i], d = saisons[i + 1];
        var sg = g.apport - g.demande, sd = d.apport - d.demande;
        var xg = x(g.annee), xd = x(d.annee);
        if (sg === 0 && sd === 0) continue;
        if ((sg >= 0) === (sd >= 0)) {
          polygones.push({
            classe: sg < 0 ? 'deficit' : 'excedent',
            points: [[xg, y(g.apport)], [xd, y(d.apport)], [xd, y(d.demande)], [xg, y(g.demande)]]
          });
          continue;
        }
        var t = sg / (sg - sd);
        var xc = xg + t * (xd - xg);
        var yc = y(g.apport + t * (d.apport - g.apport));
        polygones.push({
          classe: sg < 0 ? 'deficit' : 'excedent',
          points: [[xg, y(g.apport)], [xc, yc], [xg, y(g.demande)]]
        });
        polygones.push({
          classe: sd < 0 ? 'deficit' : 'excedent',
          points: [[xc, yc], [xd, y(d.apport)], [xd, y(d.demande)]]
        });
      }
      return polygones;
    }

    function rendre() {
      var c = cadrage(cadre, 360, 300);
      etat.etroit = c.etroit;
      cadre.textContent = '';

      var valeurs = [];
      saisons.forEach(function (s) { valeurs.push(s.apport, s.demande); });
      var y0 = Math.min.apply(null, valeurs) * 0.92;
      var y1 = Math.max.apply(null, valeurs) * 1.04;
      var x0 = saisons[0].annee, x1 = saisons[saisons.length - 1].annee;

      var M = c.marges;
      var largeurTrace = c.largeur - M.gauche - M.droite;
      var hauteurTrace = c.hauteur - M.haut - M.bas;
      function x(a) { return M.gauche + (a - x0) / (x1 - x0) * largeurTrace; }
      function y(v) { return M.haut + (y1 - v) / (y1 - y0) * hauteurTrace; }

      var svg = el('svg', {
        viewBox: '0 0 ' + c.largeur + ' ' + c.hauteur,
        preserveAspectRatio: 'xMidYMid meet', role: 'img'
      });
      svg.setAttribute('aria-label',
        'Pluie et évapotranspiration cumulées sur la saison, année après année.');

      graduations(y0, y1, c.etroit ? 4 : 6).forEach(function (v) {
        svg.appendChild(el('line', {
          x1: M.gauche, x2: c.largeur - M.droite, y1: y(v), y2: y(v), class: 'viz-grille-ligne'
        }));
        var t = el('text', { x: M.gauche - 8, y: y(v) + 4, class: 'viz-graduation y' });
        t.textContent = v;
        svg.appendChild(t);
      });
      graduations(x0, x1, c.etroit ? 4 : 8).forEach(function (a) {
        if (a < x0 || a > x1) return;
        var t = el('text', { x: x(a), y: c.hauteur - M.bas + 18, class: 'viz-graduation x' });
        t.textContent = a;
        svg.appendChild(t);
      });
      svg.appendChild(el('line', {
        x1: M.gauche, x2: c.largeur - M.droite,
        y1: c.hauteur - M.bas, y2: c.hauteur - M.bas, class: 'viz-axe-ligne'
      }));

      bandes(x, y).forEach(function (p) {
        svg.appendChild(el('path', { d: chemin(p.points) + ' Z', class: 'bilan-bande ' + p.classe }));
      });

      [['apport', 'apport'], ['demande', 'demande']].forEach(function (paire) {
        svg.appendChild(el('path', {
          d: chemin(saisons.map(function (s) { return [x(s.annee), y(s[paire[0]])]; })),
          class: 'bilan-courbe ' + paire[1]
        }));
        var t = donnees.tendances[paire[0]];
        if (t) {
          svg.appendChild(el('path', {
            d: chemin(t.courbe.map(function (p) { return [x(p.annee), y(p.valeur)]; })),
            class: 'bilan-droite ' + paire[1]
          }));
        }
      });

      var survol = el('g', {});
      svg.appendChild(survol);
      cadre.appendChild(svg);

      svg.addEventListener('pointermove', function (evt) {
        var boite = svg.getBoundingClientRect();
        var ratio = (evt.clientX - boite.left) / boite.width * c.largeur;
        var annee = Math.round(x0 + (ratio - M.gauche) / largeurTrace * (x1 - x0));
        var s = saisons.find(function (v) { return v.annee === annee; });
        survol.textContent = '';
        if (!s) { bulle.dataset.visible = 'false'; return; }
        survol.appendChild(el('line', {
          x1: x(annee), x2: x(annee), y1: M.haut, y2: c.hauteur - M.bas, class: 'climat-curseur'
        }));
        remplirBulle(racine, bulle, String(annee), [
          { cle: 'apport', nom: 'Reçu', mesure: s.apport + ' mm', second: '' },
          { cle: 'demande', nom: 'Réclamé', mesure: s.demande + ' mm', second: '' },
          { cle: 'apport', nom: 'Bilan', mesure: (s.bilan >= 0 ? '+' : '') + s.bilan + ' mm', second: '' }
        ]);
        placerBulle(racine, bulle, evt);
      });
      svg.addEventListener('pointerleave', function () {
        survol.textContent = '';
        bulle.dataset.visible = 'false';
      });
    }

    [['apport', 'Reçu (pluie)'], ['demande', 'Réclamé (évapotranspiration)']].forEach(function (p) {
      var t = donnees.tendances[p[0]];
      var detail = t
        ? (t.pente_par_decennie >= 0 ? '+' : '') + t.pente_par_decennie.toFixed(1) + ' mm/décennie'
          + (t.significative ? '' : ' (non significative)')
        : '';
      ajouterLegende(legende, p[0], p[1], detail, '', function () { return true; });
    });

    rendre();
    surRedimensionnement(etat, rendre);
  }

  // ---------------------------------------------------------------------------
  // Graphe 7 : l'état standardisé de chaque saison.
  // ---------------------------------------------------------------------------
  function grapheEtats() {
    var racine = document.querySelector('[data-etats]');
    var donnees = json('etats-donnees');
    if (!racine || !donnees || !donnees.etats.length) return;

    var cadre = racine.querySelector('.viz-cadre');
    var bulle = racine.querySelector('.viz-bulle');
    var etat = { cadre: cadre, etroit: false };
    var etats = donnees.etats;

    function rendre() {
      var c = cadrage(cadre, 300, 260);
      etat.etroit = c.etroit;
      cadre.textContent = '';

      var indices = etats.map(function (e) { return e.indice; });
      var borne = Math.max(2.2, Math.max.apply(null, indices.map(Math.abs)) * 1.08);
      var x0 = etats[0].annee, x1 = etats[etats.length - 1].annee;

      var M = c.marges;
      var largeurTrace = c.largeur - M.gauche - M.droite;
      var hauteurTrace = c.hauteur - M.haut - M.bas;
      var pas = largeurTrace / etats.length;
      function x(a) { return M.gauche + (a - x0) / (x1 - x0 + 1) * largeurTrace; }
      function y(v) { return M.haut + (borne - v) / (2 * borne) * hauteurTrace; }

      var svg = el('svg', {
        viewBox: '0 0 ' + c.largeur + ' ' + c.hauteur,
        preserveAspectRatio: 'xMidYMid meet', role: 'img'
      });
      svg.setAttribute('aria-label',
        'Indice standardisé de chaque saison : négatif quand elle est sèche.');

      [-2, -1, 0, 1, 2].forEach(function (v) {
        if (Math.abs(v) > borne) return;
        svg.appendChild(el('line', {
          x1: M.gauche, x2: c.largeur - M.droite, y1: y(v), y2: y(v),
          class: v === donnees.seuil_sec ? 'etat-seuil' : 'viz-grille-ligne'
        }));
        var t = el('text', { x: M.gauche - 8, y: y(v) + 4, class: 'viz-graduation y' });
        t.textContent = v;
        svg.appendChild(t);
      });
      var repere = el('text', {
        x: M.gauche + 4, y: y(donnees.seuil_sec) + 14, class: 'etat-seuil-texte'
      });
      repere.textContent = 'seuil de saison sèche';
      svg.appendChild(repere);

      graduations(x0, x1, c.etroit ? 4 : 8).forEach(function (a) {
        if (a < x0 || a > x1) return;
        var t = el('text', {
          x: x(a) + pas / 2, y: c.hauteur - M.bas + 18, class: 'viz-graduation x'
        });
        t.textContent = a;
        svg.appendChild(t);
      });

      etats.forEach(function (e) {
        // L'intensité suit la sévérité : deux écarts-types saturent la teinte.
        var force = Math.min(1, Math.abs(e.indice) / 2);
        svg.appendChild(el('rect', {
          x: x(e.annee) + 1,
          y: e.indice >= 0 ? y(e.indice) : y(0),
          width: Math.max(1, pas - 2),
          height: Math.max(1, Math.abs(y(e.indice) - y(0))),
          class: 'etat-barre ' + (e.indice < 0 ? 'sec' : 'humide'),
          style: '--force:' + force.toFixed(3)
        }));
      });

      svg.appendChild(el('line', {
        x1: M.gauche, x2: c.largeur - M.droite, y1: y(0), y2: y(0), class: 'viz-axe-ligne'
      }));

      cadre.appendChild(svg);

      svg.addEventListener('pointermove', function (evt) {
        var boite = svg.getBoundingClientRect();
        var ratio = (evt.clientX - boite.left) / boite.width * c.largeur;
        var i = Math.floor((ratio - M.gauche) / pas);
        if (i < 0 || i >= etats.length) { bulle.dataset.visible = 'false'; return; }
        var e = etats[i];
        remplirBulle(racine, bulle, String(e.annee), [{
          cle: e.indice < 0 ? 'demande' : 'apport',
          nom: e.libelle,
          mesure: (e.indice >= 0 ? '+' : '') + e.indice.toFixed(2),
          second: (e.bilan >= 0 ? '+' : '') + e.bilan + ' mm'
        }]);
        placerBulle(racine, bulle, evt);
      });
      svg.addEventListener('pointerleave', function () { bulle.dataset.visible = 'false'; });
    }

    rendre();
    surRedimensionnement(etat, rendre);
  }

  grapheTendance();
  grapheCycle();
  grapheSeuils();
  grapheGel();
  grapheRecords();
  grapheBilan();
  grapheEtats();
})();
