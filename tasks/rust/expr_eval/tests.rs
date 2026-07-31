use task::{eval, EvalError};

fn ok(expr: &str, expected: f64) {
    match eval(expr) {
        Ok(v) => assert!(
            (v - expected).abs() < 1e-9,
            "eval({expr:?}) = {v}, attendu {expected}"
        ),
        Err(e) => panic!("eval({expr:?}) a échoué avec {e:?}, attendu {expected}"),
    }
}

fn err(expr: &str, expected: EvalError) {
    assert_eq!(eval(expr), Err(expected), "pour l'entrée {expr:?}");
}

#[test]
fn addition_simple() {
    ok("1+2", 3.0);
}

#[test]
fn precedence_multiplication() {
    ok("2+3*4", 14.0);
}

#[test]
fn soustraction_associative_a_gauche() {
    ok("10-3-2", 5.0);
}

#[test]
fn division_associative_a_gauche() {
    ok("100/5/2", 10.0);
}

#[test]
fn parentheses() {
    ok("(2+3)*4", 20.0);
}

#[test]
fn parentheses_imbriquees() {
    ok("((1+2)*(3+4))", 21.0);
}

#[test]
fn unaire_moins() {
    ok("-5+3", -2.0);
}

#[test]
fn unaire_moins_repete() {
    ok("--5", 5.0);
}

#[test]
fn unaire_lie_moins_fort_que_puissance() {
    ok("-2^2", -4.0);
}

#[test]
fn puissance_associative_a_droite() {
    ok("2^3^2", 512.0);
}

#[test]
fn exposant_unaire() {
    ok("2^-1", 0.5);
}

#[test]
fn decimaux() {
    ok("1.5*2", 3.0);
    ok("0.5^2", 0.25);
}

#[test]
fn modulo() {
    ok("7%3", 1.0);
    ok("-7%3", -1.0);
}

#[test]
fn espaces_ignores() {
    ok("  1  +  2 * ( 3 - 1 )  ", 5.0);
}

#[test]
fn produit_de_negatifs() {
    ok("(-3)*(-4)", 12.0);
}

#[test]
fn erreur_entree_vide() {
    err("", EvalError::UnexpectedEnd);
}

#[test]
fn erreur_operateur_final() {
    err("2+", EvalError::UnexpectedEnd);
    err("-", EvalError::UnexpectedEnd);
}

#[test]
fn erreur_caractere_inconnu() {
    err("2 & 3", EvalError::UnexpectedChar('&'));
}

#[test]
fn erreur_operande_attendue() {
    err("1 + * 2", EvalError::UnexpectedChar('*'));
}

#[test]
fn erreur_parenthese_non_fermee() {
    err("(1+2", EvalError::UnbalancedParen);
}

#[test]
fn erreur_parenthese_en_trop() {
    err("1+2)", EvalError::UnbalancedParen);
}

#[test]
fn erreur_division_par_zero() {
    err("1/0", EvalError::DivisionByZero);
    err("1%0", EvalError::DivisionByZero);
}

#[test]
fn division_par_zero_seulement_si_exact() {
    ok("1/0.5", 2.0);
}
