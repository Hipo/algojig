package main

import (
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"io/ioutil"
	"os"

	"github.com/algorand/go-algorand/agreement"
	"github.com/algorand/go-algorand/config"
	"github.com/algorand/go-algorand/crypto"
	"github.com/algorand/go-algorand/data/basics"
	"github.com/algorand/go-algorand/data/bookkeeping"
	"github.com/algorand/go-algorand/data/transactions"
	"github.com/algorand/go-algorand/data/transactions/logic"
	"github.com/algorand/go-algorand/data/transactions/verify"
	"github.com/algorand/go-algorand/ledger"
	"github.com/algorand/go-algorand/ledger/ledgercore"
	"github.com/algorand/go-algorand/logging"
	"github.com/algorand/go-algorand/protocol"
	"github.com/algorand/go-codec/codec"
)

var genesisHash crypto.Digest
var rewardsPool basics.Address

func init() {
	copy(genesisHash[:], []byte("\x9b\x01\x08\xe3\xf2Q-6\x1f\xd9\x01z\x9c\x07\x8a`\xe3\x8dR\xc5D\xe9<W\xeb\xd89\xa9\xb9\xdfw@"))
	copy(rewardsPool[:], []byte("\x85\x0b{X.k<6l\xe2[\xc0\xae/\x10N\xa3?\x9f\xb9\xb6\xf47\xf6\x10\x1fZ<@Zp<"))

}

func readFile(filename string) ([]byte, error) {
	if filename == "-" {
		return ioutil.ReadAll(os.Stdin)
	}
	return ioutil.ReadFile(filename)
}

func compile(fname string) {
	src, _ := readFile(fname)
	ops, err := logic.AssembleString(string(src))
	if err != nil {
		ops.ReportProblems("", os.Stderr)
		os.Exit(1)
	}
	fmt.Println(base64.StdEncoding.EncodeToString(ops.Program))
	sourcemap := logic.GetSourceMap([]string{""}, ops.OffsetToLine)
	s, _ := json.Marshal(sourcemap)
	fmt.Print(string(s))
}

func main() {
	// fn := fmt.Sprintf("/tmp/%s.%d.sqlite3", "jig_ledger", crypto.RandUint64())
	fn := "/tmp/jig/jig_ledger.sqlite3"
	switch os.Args[1] {
	case "init":
		os.RemoveAll("/tmp/jig")
		os.MkdirAll("/tmp/jig", 0777)
		initLedger(fn)
	case "eval":
		evalTransactions(fn)
	case "read":
		readAccounts(fn)
	case "compile":
		compile(os.Args[2])
	default:
		fmt.Println("expected 'init' or 'eval' subcommands")
		os.Exit(1)
	}
}

func initLedger(fn string) {
	accounts := make(map[basics.Address]basics.AccountData)
	ledger := makeJigLedger(fn, accounts)
	prev, _ := ledger.BlockHdr(ledger.Latest())
	block := bookkeeping.MakeBlock(prev)
	ledger.AddBlock(block, agreement.Certificate{})
	ledger.Close()
}

func evalTransactions(fn string) {
	ledger := openJigLedger(fn)

	prev, _ := ledger.BlockHdr(ledger.Latest())
	block := bookkeeping.MakeBlock(prev)
	eval, err := ledger.StartEvaluator(block.BlockHeader, 0, 0)
	if err != nil {
		panic(err)
	}

	var stxns []transactions.SignedTxn
	f, _ := os.Open("/tmp/jig/stxns")
	dec := protocol.NewDecoder(f)
	for {
		var st transactions.SignedTxn
		err := dec.Decode(&st)
		if err == io.EOF {
			break
		}
		if err != nil {
			fmt.Fprint(os.Stderr, err.Error())
			os.Exit(1)
		}
		stxns = append(stxns, st)
	}
	txgroups := bookkeeping.SignedTxnsToGroups(stxns)

	for _, txgroup := range txgroups {
		_, err = verify.TxnGroup(txgroup, prev, ledger.VerifiedTransactionCache())
		if err != nil {
			fmt.Fprint(os.Stderr, err.Error())
			os.Exit(1)
		}

		err = eval.TestTransactionGroup(txgroup)
		if err != nil {
			fmt.Fprint(os.Stderr, err.Error())
			os.Exit(1)
		}
		txads := make([]transactions.SignedTxnWithAD, 0, len(txgroup))
		for _, txn := range txgroup {
			txad := transactions.SignedTxnWithAD{SignedTxn: txn, ApplyData: transactions.ApplyData{}}
			txads = append(txads, txad)
		}
		err = eval.TransactionGroup(txads)
		if err != nil {
			fmt.Fprint(os.Stderr, err.Error())
			os.Exit(1)
		}
	}

	newBlock, err := eval.GenerateBlock()
	if err != nil {
		fmt.Fprint(os.Stderr, err.Error())
		os.Exit(1)
	}

	block = newBlock.Block()
	err = ledger.AddBlock(block, agreement.Certificate{Round: block.Round()})
	if err != nil {
		fmt.Fprint(os.Stderr, err.Error())
		os.Exit(1)
	}

	<-ledger.Wait(block.Round())

	ledger.Close()

	// For some reason updates are NOT written to the accounts tracker db here.

	ledger = openJigLedger(fn)
	r1, r2 := ledger.LatestCommitted()
	fmt.Fprint(os.Stderr, r1, r2)
	ledger.Close()

	data, err := encode(block)
	if err != nil {
		panic(err)
	}

	fmt.Print(string(data))
	os.Exit(0)
}

func readAccounts(fn string) {
	ledger := openJigLedger(fn)

	var address basics.Address
	copy(address[:], []byte("\x12P\x86Zh\xad\xc3\x00 \xbe\xfa2\xc43\x14l\xd5\xb0\xb7\xdcpFO\xb8\x89\xc1\xd3]\x1d\x97\xf6\xc8"))

	data, r, balance, err := ledger.LookupLatest(address)
	if err != nil {
		fmt.Fprint(os.Stderr, err.Error())
		os.Exit(1)
	}
	fmt.Fprint(os.Stderr, r, data, balance)
	os.Exit(1)

}

func encode(obj interface{}) ([]byte, error) {
	var output []byte
	enc := codec.NewEncoderBytes(&output, protocol.CodecHandle)

	err := enc.Encode(obj)
	if err != nil {
		return nil, fmt.Errorf("failed to encode object: %v", err)
	}
	return output, nil
}

func makeJigLedger(fn string, initAccounts map[basics.Address]basics.AccountData) *ledger.Ledger {
	var poolData basics.AccountData
	poolData.MicroAlgos.Raw = 1 << 32
	initAccounts[rewardsPool] = poolData

	initBlock := bookkeeping.Block{
		BlockHeader: bookkeeping.BlockHeader{
			GenesisID:   "algojig",
			GenesisHash: genesisHash,
			UpgradeState: bookkeeping.UpgradeState{
				CurrentProtocol: protocol.ConsensusFuture,
			},
			RewardsState: bookkeeping.RewardsState{
				FeeSink:     rewardsPool,
				RewardsPool: rewardsPool,
			},
		},
	}

	var err error
	genesisInitState := ledgercore.InitState{Block: initBlock, Accounts: initAccounts, GenesisHash: genesisHash}
	cfg := config.GetDefaultLocal()
	cfg.Archival = true
	cfg.LedgerSynchronousMode = 3
	cfg.AccountsRebuildSynchronousMode = 3
	log := logging.Base()
	log.SetLevel(logging.Debug)
	l, err := ledger.OpenLedger(log, fn, false, genesisInitState, cfg)
	if err != nil {
		panic(err)
	}
	return l
}

func openJigLedger(fn string) *ledger.Ledger {
	return makeJigLedger(fn, make(map[basics.Address]basics.AccountData))
}
