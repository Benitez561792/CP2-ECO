

SET SERVEROUTPUT ON SIZE UNLIMITED;

DECLARE
    CURSOR c_participantes IS
        SELECT
            U.ID         AS usuario_id,
            U.NOME       AS nome,
            U.SALDO      AS saldo_atual,
            I.ID         AS inscricao_id,
            I.VALOR_PAGO AS valor_pago,
            I.TIPO       AS tipo
        FROM   USUARIOS  U
        JOIN   INSCRICOES I ON U.ID = I.USUARIO_ID
        WHERE  I.STATUS = 'PRESENT'
        ORDER  BY U.ID, I.ID;

 
    v_percentual      NUMBER(5,2);
    v_cashback        NUMBER(10,2);
    v_total_presencas NUMBER;
    v_contador        NUMBER        := 0;
    v_total_credito   NUMBER(10,2)  := 0;
    v_motivo          VARCHAR2(400);
    v_regra           VARCHAR2(100);

    -- Exceção customizada: valor de inscrição inválido
    ex_valor_invalido EXCEPTION;
    PRAGMA EXCEPTION_INIT(ex_valor_invalido, -20001);

BEGIN
    DBMS_OUTPUT.PUT_LINE('============================================================');
    DBMS_OUTPUT.PUT_LINE('  ECO-AWARENESS 2026 | Motor de Cashback Progressivo');
    DBMS_OUTPUT.PUT_LINE('  Iniciando: ' || TO_CHAR(SYSDATE, 'DD/MM/YYYY HH24:MI:SS'));
    DBMS_OUTPUT.PUT_LINE('============================================================');


    FOR r IN c_participantes LOOP


        SELECT COUNT(*)
          INTO v_total_presencas
          FROM INSCRICOES
         WHERE USUARIO_ID = r.usuario_id
           AND STATUS     = 'PRESENT';


        IF r.valor_pago <= 0 THEN
            RAISE_APPLICATION_ERROR(
                -20001,
                'Valor pago invalido para inscricao ID=' || r.inscricao_id
                || ' | Usuario: ' || r.nome
            );
        END IF;

    
        IF v_total_presencas > 3 THEN
            v_percentual := 25;
            v_regra      := 'ATIVISTA (>3 presencas)';
        ELSIF UPPER(r.tipo) = 'VIP' THEN
            v_percentual := 20;
            v_regra      := 'INGRESSO VIP';
        ELSE
            v_percentual := 10;
            v_regra      := 'TAXA PISO';
        END IF;

        v_cashback := ROUND(r.valor_pago * v_percentual / 100, 2);

        DBMS_OUTPUT.PUT_LINE('');
        DBMS_OUTPUT.PUT_LINE('  Usuario   : ' || r.nome);
        DBMS_OUTPUT.PUT_LINE('  Inscricao : #' || r.inscricao_id || ' | Tipo: ' || r.tipo);
        DBMS_OUTPUT.PUT_LINE('  Presencas : ' || v_total_presencas || ' | Regra: ' || v_regra);
        DBMS_OUTPUT.PUT_LINE('  Valor pago: R$ ' || r.valor_pago
                             || ' | Cashback (' || v_percentual || '%): R$ ' || v_cashback);

   
        v_motivo := 'CASHBACK ' || v_percentual || '% | '
                    || 'Regra: '            || v_regra            || ' | '
                    || 'Presencas totais: ' || v_total_presencas  || ' | '
                    || 'Tipo insc.: '       || r.tipo             || ' | '
                    || 'Valor pago: R$ '    || r.valor_pago       || ' | '
                    || 'Cashback: R$ '      || v_cashback;

        INSERT INTO LOG_AUDITORIA (INSCRICAO_ID, MOTIVO, DATA)
        VALUES (r.inscricao_id, v_motivo, SYSDATE);


        UPDATE USUARIOS
           SET SALDO = SALDO + v_cashback
         WHERE ID = r.usuario_id;

        v_contador      := v_contador + 1;
        v_total_credito := v_total_credito + v_cashback;

    END LOOP;

    COMMIT;

    DBMS_OUTPUT.PUT_LINE('');
    DBMS_OUTPUT.PUT_LINE('============================================================');
    DBMS_OUTPUT.PUT_LINE('  RESUMO FINAL');
    DBMS_OUTPUT.PUT_LINE('  Inscricoes processadas : ' || v_contador);
    DBMS_OUTPUT.PUT_LINE('  Total creditado        : R$ '
                         || TO_CHAR(v_total_credito, 'FM99999990.00'));
    DBMS_OUTPUT.PUT_LINE('  Status transacional    : COMMIT realizado');
    DBMS_OUTPUT.PUT_LINE('============================================================');

EXCEPTION
    WHEN ex_valor_invalido THEN
        ROLLBACK;
        DBMS_OUTPUT.PUT_LINE('');
        DBMS_OUTPUT.PUT_LINE('[ERRO] Dados invalidos detectados — ROLLBACK executado.');
        DBMS_OUTPUT.PUT_LINE('Detalhe: ' || SQLERRM);

    WHEN OTHERS THEN
        ROLLBACK;
        DBMS_OUTPUT.PUT_LINE('');
        DBMS_OUTPUT.PUT_LINE('[ERRO] Falha inesperada — ROLLBACK executado.');
        DBMS_OUTPUT.PUT_LINE('Codigo  : ' || SQLCODE);
        DBMS_OUTPUT.PUT_LINE('Mensagem: ' || SQLERRM);
END;
/


SELECT
    U.NOME,
    COUNT(CASE WHEN I.STATUS = 'PRESENT' THEN 1 END) AS presencas,
    U.SALDO                                           AS saldo_cashback
FROM   USUARIOS U
LEFT JOIN INSCRICOES I ON U.ID = I.USUARIO_ID
GROUP  BY U.NOME, U.SALDO
ORDER  BY U.SALDO DESC;
